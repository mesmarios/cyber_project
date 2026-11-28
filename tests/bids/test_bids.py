import unittest
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier

from app import create_app
from app.core.database import get_db


BUYER_ID = 15
SECOND_BUYER_ID = 16
SELLER_ID = 17
TEST_CSRF_TOKEN = "bidding-test-token"


class BiddingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config["TESTING"] = True

    def setUp(self):
        self.auction_id = self.write(
            """
            INSERT INTO auctions (seller_id, title, description, starting_price, ends_at)
            VALUES (%s, 'Test Auction', 'Bidding test fixture', 20.00,
                    UTC_TIMESTAMP() + INTERVAL 1 DAY)
            """,
            (SELLER_ID,),
        )
        self.url = f"/auctions/{self.auction_id}/bids"
        self.addCleanup(self.delete_auction)

    def write(self, query, parameters):
        with self.app.app_context():
            connection = get_db()
            with connection.cursor() as cursor:
                cursor.execute(query, parameters)
                row_id = cursor.lastrowid
            connection.commit()
            return row_id

    def delete_auction(self):
        with self.app.app_context():
            connection = get_db()
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM bids WHERE auction_id = %s", (self.auction_id,))
                cursor.execute("DELETE FROM auctions WHERE id = %s", (self.auction_id,))
            connection.commit()

    def saved_bids(self):
        with self.app.app_context():
            with get_db().cursor() as cursor:
                cursor.execute(
                    "SELECT bidder_id, amount FROM bids WHERE auction_id = %s ORDER BY id",
                    (self.auction_id,),
                )
                return cursor.fetchall()

    def signed_in_client(self, user_id=BUYER_ID, token=TEST_CSRF_TOKEN):
        client = self.app.test_client()
        # Auth will set this same session key when its login route is added.
        with client.session_transaction() as session:
            session["user_id"] = user_id
            if token is not None:
                session["bids_csrf_token"] = token
        return client

    def test_displays_starting_price_highest_bid_and_bid_history(self):
        for amount in (Decimal("22.50"), Decimal("35.00")):
            self.write(
                "INSERT INTO bids (auction_id, bidder_id, amount) VALUES (%s, %s, %s)",
                (self.auction_id, BUYER_ID, amount),
            )

        response = self.app.test_client().get(self.url)
        page = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Test Auction", page)
        self.assertIn("Starting price: 20.00", page)
        self.assertRegex(page, r"Current highest bid:\s+35\.00")
        self.assertIn("<li>22.50 on", page)
        self.assertIn("<li>35.00 on", page)
        self.assertIn("Sign in to place a bid.", page)
        self.assertNotIn('name="amount"', page)

    def test_accepts_bid_and_uses_session_identity(self):
        client = self.signed_in_client(token=None)
        page = client.get(self.url).get_data(as_text=True)
        with client.session_transaction() as session:
            token = session["bids_csrf_token"]
        self.assertIn(f'name="csrf_token" value="{token}"', page)

        response = client.post(
            self.url,
            data={"amount": "25.75", "csrf_token": token, "bidder_id": SELLER_ID},
        )
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.location, self.url)
        confirmation = client.get(response.location).get_data(as_text=True)
        self.assertIn("Your bid was accepted.", confirmation)
        self.assertRegex(confirmation, r"Current highest bid:\s+25\.75")
        self.assertEqual(self.saved_bids(), ((BUYER_ID, Decimal("25.75")),))

    def test_redirects_unauthenticated_bidder_to_login(self):
        response = self.app.test_client().post(self.url, data={"amount": "25.00"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, "/login")
        self.assertEqual(self.saved_bids(), ())

    def test_rejects_seller_bid(self):
        self.assert_rejected(self.signed_in_client(SELLER_ID), 403, "your own auction")

    def test_rejects_bid_at_or_below_the_minimum(self):
        client = self.signed_in_client()
        response = client.post(self.url, data={"amount": "20.00", "csrf_token": TEST_CSRF_TOKEN})
        self.assertEqual(response.status_code, 400)
        page = response.get_data(as_text=True)
        self.assertIn('<p role="alert">Your bid must be higher than 20.00.</p>', page)
        self.assertIn('name="amount"', page)
        self.assertEqual(self.saved_bids(), ())

    def test_rejects_bid_for_closed_auction(self):
        self.write("UPDATE auctions SET status = 'closed' WHERE id = %s", (self.auction_id,))
        self.assert_rejected(self.signed_in_client(), 400, "auction is closed")

    def test_rejects_bid_for_expired_auction(self):
        self.write(
            "UPDATE auctions SET ends_at = UTC_TIMESTAMP() WHERE id = %s",
            (self.auction_id,),
        )
        self.assert_rejected(self.signed_in_client(), 400, "auction has expired")

    def test_accepts_only_one_of_two_competing_equal_bids(self):
        ready = Barrier(2, timeout=5)

        def submit_bid(user_id):
            client = self.signed_in_client(user_id)
            ready.wait()
            return client.post(self.url, data={"amount": "25.00", "csrf_token": TEST_CSRF_TOKEN})

        with ThreadPoolExecutor(max_workers=2) as executor:
            submissions = [
                executor.submit(submit_bid, BUYER_ID),
                executor.submit(submit_bid, SECOND_BUYER_ID),
            ]
            responses = [submission.result(timeout=10) for submission in submissions]

        self.assertCountEqual([response.status_code for response in responses], [303, 400])
        rejected = next(response for response in responses if response.status_code == 400)
        self.assertIn("higher than 25.00", rejected.get_data(as_text=True))
        winner_id = BUYER_ID if responses[0].status_code == 303 else SECOND_BUYER_ID
        self.assertEqual(self.saved_bids(), ((winner_id, Decimal("25.00")),))

    def test_rejects_invalid_monetary_amounts(self):
        client = self.signed_in_client()
        for amount in ("", "NaN", "2.5e1", "25.001", "0", "-25", "100000000"):
            with self.subTest(amount=amount):
                self.assert_rejected(client, 400, "Enter", amount=amount)

    def test_hides_private_auction_from_bidders(self):
        self.write("UPDATE auctions SET is_public = FALSE WHERE id = %s", (self.auction_id,))
        client = self.signed_in_client()
        self.assertEqual(client.get(self.url).status_code, 404)
        self.assert_rejected(client, 404, "Public auction not found")

    def test_requires_matching_csrf_token(self):
        client = self.signed_in_client()
        for token in ("", "invalid", "é"):
            with self.subTest(token=token):
                self.assert_rejected(client, 400, "try submitting the form again", token=token)

    def assert_rejected(self, client, status, message, *, amount="25.00", token=TEST_CSRF_TOKEN):
        response = client.post(self.url, data={"amount": amount, "csrf_token": token})
        self.assertEqual(response.status_code, status)
        self.assertIn(message, response.get_data(as_text=True))
        self.assertEqual(self.saved_bids(), ())


if __name__ == "__main__":
    unittest.main()
