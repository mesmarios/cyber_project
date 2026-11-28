import re
from datetime import datetime, timezone
from decimal import Decimal
from secrets import compare_digest, token_urlsafe

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from pymysql import MySQLError
from pymysql.cursors import DictCursor
from werkzeug.exceptions import BadRequest, Forbidden

from app.core.database import get_db
from app.core.security import login_required

bp = Blueprint("bids", __name__, template_folder="templates")
MAX_BID = Decimal("99999999.99")  # Largest value in a DECIMAL(10,2) column.


def find_public_auction(cursor, auction_id, *, lock=False):
    query = """
        SELECT title, seller_id, starting_price, status, ends_at
        FROM auctions
        WHERE id = %s AND is_public = TRUE
    """
    if lock:
        query += "FOR UPDATE"
    cursor.execute(query, (auction_id,))
    auction = cursor.fetchone()
    if auction is None:
        abort(404, description="Public auction not found.")
    return auction


def bidding_restriction(auction, user_id):
    if auction["status"] != "open":
        return "This auction is closed.", 400
    # MariaDB returns ends_at as a naive datetime stored in UTC.
    if auction["ends_at"] <= datetime.now(timezone.utc).replace(tzinfo=None):
        return "This auction has expired.", 400
    if user_id is None:
        return "Sign in to place a bid.", 401
    if auction["seller_id"] == user_id:
        return "You cannot bid on your own auction.", 403
    return None


@bp.get("/auctions/<int:auction_id>/bids")
def list_bids(auction_id):
    return render_bids_page(auction_id)


def render_bids_page(auction_id, error=None):
    try:
        with get_db().cursor(DictCursor) as cursor:
            auction = find_public_auction(cursor, auction_id)
            cursor.execute(
                """
                SELECT amount, created_at
                FROM bids
                WHERE auction_id = %s
                ORDER BY amount DESC, id DESC
                """,
                (auction_id,),
            )
            bids = cursor.fetchall()
    except MySQLError:
        current_app.logger.exception("Could not load auction bids")
        abort(503, description="Bids are temporarily unavailable.")

    restriction = bidding_restriction(auction, session.get("user_id"))
    csrf_token = None
    if restriction is None:
        csrf_token = session.get("bids_csrf_token")
        if csrf_token is None:
            csrf_token = token_urlsafe()
            session["bids_csrf_token"] = csrf_token

    return render_template(
        "bids/index.html",
        auction=auction,
        auction_id=auction_id,
        bids=bids,
        highest_bid=bids[0]["amount"] if bids else None,
        restriction=restriction[0] if restriction else None,
        csrf_token=csrf_token,
        error=error,
    )


def read_bid_amount():
    value = request.form.get("amount", "").strip()
    if not re.fullmatch(r"(?:[0-9]+(?:\.[0-9]{0,2})?|\.[0-9]{1,2})", value):
        abort(400, description="Enter a positive amount with up to two decimal places.")
    amount = Decimal(value)
    if not 0 < amount <= MAX_BID:
        abort(400, description=f"Enter an amount between 0.01 and {MAX_BID}.")
    return amount


def save_bid(auction_id, bidder_id, amount):
    connection = get_db()
    try:
        connection.begin()
        with connection.cursor(DictCursor) as cursor:
            # Lock the auction first so concurrent submissions take turns.
            auction = find_public_auction(cursor, auction_id, lock=True)
            restriction = bidding_restriction(auction, bidder_id)
            if restriction:
                message, status = restriction
                abort(status, description=message)

            # The first consistent read starts after the auction lock is acquired.
            cursor.execute(
                "SELECT MAX(amount) AS highest_bid FROM bids WHERE auction_id = %s",
                (auction_id,),
            )
            highest_bid = cursor.fetchone()["highest_bid"]
            minimum = auction["starting_price"]
            if highest_bid is not None:
                minimum = max(minimum, highest_bid)
            if amount <= minimum:
                abort(400, description=f"Your bid must be higher than {minimum:.2f}.")

            cursor.execute(
                "INSERT INTO bids (auction_id, bidder_id, amount) VALUES (%s, %s, %s)",
                (auction_id, bidder_id, amount),
            )
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def check_csrf_token():
    # The token prevents other sites from submitting a bid with this session.
    expected_token = session.get("bids_csrf_token")
    submitted_token = request.form.get("csrf_token", "")
    if not expected_token or not compare_digest(
        expected_token.encode(), submitted_token.encode()
    ):
        abort(400, description="Open the bidding page and try submitting the form again.")


@bp.post("/auctions/<int:auction_id>/bids")
@login_required
def place_bid(auction_id):
    try:
        check_csrf_token()
        amount = read_bid_amount()
        save_bid(auction_id, session["user_id"], amount)
    except (BadRequest, Forbidden) as error:
        return render_bids_page(auction_id, error=error.description), error.code
    except MySQLError:
        current_app.logger.exception("Could not save auction bid")
        abort(503, description="Bids are temporarily unavailable. Please try again.")

    flash("Your bid was accepted.", "bids")
    return redirect(url_for("bids.list_bids", auction_id=auction_id), code=303)
