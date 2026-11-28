# Bidding

`GET /auctions/<id>/bids` shows the starting price, highest bid, and bid history for a public auction. The form appears for signed-in users who can bid. `POST` reads the bid amount and the form's CSRF token, and takes the bidder ID from the Flask session. Successful submissions redirect to the bidding page with confirmation. Rejected bids for public auctions display an error on the page.

Each submission starts a MariaDB transaction and locks the auction row before checking the deadline and reading the highest bid. This makes competing submissions for the same auction take turns and ensures each one sees the bids committed before it acquired the lock.

`POST /auctions/<id>/close` uses the same lock. The seller or an active administrator can close the auction. The close form appears on the public bidding page for its seller and uses the module's CSRF token. The highest eligible bid wins. An eligible bid beats the starting price, comes from someone other than the seller, and was recorded before the deadline. Ties go to the smallest bid ID. Closing without an eligible bid leaves the winner empty.

`GET /auctions/<id>/winner-address` shows the delivery address to the seller or an active administrator after the auction closes with a winner. The address is read from `addresses` using the stored winner ID. The public bidding page displays only the winning username and amount.

`GET /profile/<user_id>/address` is the isolated IDOR endpoint in the Vulnerable Version. It requires a signed-in session and uses a parameterized query, but intentionally omits the check that the requested user ID belongs to the signed-in user. It displays only the fictional username, user ID, and delivery-address fields.

The app factory already registers the bidding Blueprint. The shared login helper redirects signed-out users to `/login`, which the Auth module needs to provide.

## Run the tests

Use an isolated test deployment with the repository's shared schema and demo seed loaded. The tests create and remove their own auctions and use the seeded bidder accounts. From an environment with the app's database settings and dependencies available, run the following from the repository root.

```sh
python -B -m unittest discover -s tests/bids -v
```

For a running Compose test project built from this checkout, the web container can read the test file from standard input. Substitute the name of your test project if needed.

```sh
docker compose -p student-auctions-bids-test exec -T web \
    python -B - -v < tests/bids/test_bids.py
```
