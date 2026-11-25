"""Read-only integration tests against the local MariaDB demo seed.

Compatible with pytest; also runnable with standard-library unittest.
Vulnerable-stage assertions must be revised when the secure fix is introduced.
"""

import unittest

from app import create_app


class AuctionSearchTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config.update(TESTING=True)
        self.client = self.app.test_client()

    def search(self, q=None):
        query = {} if q is None else {"q": q}
        response = self.client.get("/auctions", query_string=query)
        return response, response.get_data(as_text=True)

    def test_public_list_includes_open_and_closed_auctions(self):
        response, html = self.search()
        self.assertEqual(response.status_code, 200)
        self.assertIn('data-auction-id="101"', html)
        self.assertIn('data-auction-id="102"', html)
        self.assertNotIn('data-auction-id="103"', html)
        self.assertIn("150.00 EUR", html)

    def test_search_matches_partial_title(self):
        response, html = self.search("Lap")
        self.assertEqual(response.status_code, 200)
        self.assertIn('data-auction-id="101"', html)
        self.assertNotIn('data-auction-id="102"', html)
        self.assertNotIn('data-auction-id="103"', html)

    def test_blank_search_lists_public_auctions(self):
        response, html = self.search("   ")
        self.assertEqual(response.status_code, 200)
        self.assertIn('data-auction-id="101"', html)
        self.assertNotIn('data-auction-id="103"', html)

    def test_private_title_search_does_not_return_private_record(self):
        response, html = self.search("PRIVATE_DEMO_01")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('data-auction-id="103"', html)
        self.assertIn("No auctions found.", html)

    def test_unicode_no_match(self):
        response, html = self.search("ανύπαρκτο αντικείμενο")
        self.assertEqual(response.status_code, 200)
        self.assertIn("No auctions found.", html)
        self.assertIn("ανύπαρκτο αντικείμενο", html)

    def test_query_is_html_escaped(self):
        response, html = self.search('<script>alert("demo")</script>')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_malformed_quote_returns_400_without_sql_details(self):
        response, html = self.search("'")
        self.assertEqual(response.status_code, 400)
        self.assertIn("The search could not be processed", html)
        self.assertNotIn("SELECT", html)
        self.assertNotIn("Traceback", html)

    def test_vulnerable_sqli_exposes_private_demo(self):
        # MariaDB's # comment remains valid after the search trims whitespace.
        response, html = self.search("' OR 1=1 #")
        self.assertEqual(response.status_code, 200)
        self.assertIn('data-auction-id="103"', html)
        self.assertIn("PRIVATE_DEMO_01", html)


if __name__ == "__main__":
    unittest.main()
