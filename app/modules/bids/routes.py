import re
from datetime import datetime, timezone
from decimal import Decimal
from secrets import compare_digest, token_urlsafe

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    make_response,
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


def find_auction(cursor, auction_id, *, public_only=False, lock=False):
    query = """
        SELECT title, seller_id, starting_price, is_public, status, ends_at, winner_user_id
        FROM auctions
        WHERE id = %s
    """
    if public_only:
        query += " AND is_public = TRUE"
    if lock:
        query += " FOR UPDATE"
    cursor.execute(query, (auction_id,))
    auction = cursor.fetchone()
    if auction is None:
        message = "Public auction not found." if public_only else "Auction not found."
        abort(404, description=message)
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
            auction = find_auction(cursor, auction_id, public_only=True)
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
            winner = None
            if auction["status"] == "closed" and auction["winner_user_id"] is not None:
                winner = find_winning_bid(cursor, auction_id, auction, auction["winner_user_id"])
    except MySQLError:
        current_app.logger.exception("Could not load auction bids")
        abort(503, description="Bids are temporarily unavailable.")

    user_id = session.get("user_id")
    restriction = bidding_restriction(auction, user_id)
    is_seller = user_id == auction["seller_id"]
    can_close = is_seller and auction["status"] == "open"
    csrf_token = None
    if restriction is None or can_close:
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
        winner=winner,
        can_close=can_close,
        show_winner_address=is_seller,
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
            auction = find_auction(cursor, auction_id, public_only=True, lock=True)
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
                """
                INSERT INTO bids (auction_id, bidder_id, amount)
                SELECT %s, %s, %s FROM DUAL WHERE UTC_TIMESTAMP() < %s
                """,
                (auction_id, bidder_id, amount, auction["ends_at"]),
            )
            # The deadline can pass while the highest bid is being checked.
            if cursor.rowcount == 0:
                abort(400, description="This auction has expired.")
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


def require_auction_manager(cursor, auction, user_id):
    cursor.execute("SELECT role FROM users WHERE id = %s AND is_active = TRUE", (user_id,))
    user = cursor.fetchone()
    if user and (auction["seller_id"] == user_id or user["role"] == "admin"):
        return
    if not auction["is_public"]:
        abort(404, description="Auction not found.")
    abort(403, description="Only the seller or an administrator can access this action.")


def find_winning_bid(cursor, auction_id, auction, winner_user_id=None):
    query = """
        SELECT bids.bidder_id, bids.amount, users.username
        FROM bids JOIN users ON users.id = bids.bidder_id
        WHERE bids.auction_id = %s AND bids.bidder_id <> %s
          AND bids.amount > %s AND bids.created_at < %s
    """
    parameters = (auction_id, auction["seller_id"], auction["starting_price"], auction["ends_at"])
    if winner_user_id is not None:
        query += " AND bids.bidder_id = %s"
        parameters += (winner_user_id,)
    # Equal amounts go to the earliest recorded bid ID.
    query += " ORDER BY bids.amount DESC, bids.id ASC LIMIT 1"
    cursor.execute(query, parameters)
    return cursor.fetchone()


def close_auction_transaction(auction_id, user_id):
    connection = get_db()
    try:
        connection.begin()
        with connection.cursor(DictCursor) as cursor:
            # Bid submission takes this same lock before it reads or writes bids.
            auction = find_auction(cursor, auction_id, lock=True)
            require_auction_manager(cursor, auction, user_id)
            if auction["status"] != "open":
                abort(400, description="This auction is already closed.")

            winner = find_winning_bid(cursor, auction_id, auction)
            cursor.execute(
                "UPDATE auctions SET status = 'closed', winner_user_id = %s WHERE id = %s",
                (winner["bidder_id"] if winner else None, auction_id),
            )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return auction, winner


@bp.post("/auctions/<int:auction_id>/close")
@login_required
def close_auction(auction_id):
    check_csrf_token()
    try:
        auction, winner = close_auction_transaction(auction_id, session["user_id"])
    except MySQLError:
        current_app.logger.exception("Could not close auction")
        abort(503, description="The auction could not be closed. Please try again.")

    if auction["is_public"]:
        flash("Auction closed.", "bids")
        return redirect(url_for("bids.list_bids", auction_id=auction_id), code=303)
    return render_template(
        "bids/closed.html",
        auction=auction,
        auction_id=auction_id,
        winner=winner,
        show_winner_address=True,
    )


@bp.get("/auctions/<int:auction_id>/winner-address")
@login_required
def winner_address(auction_id):
    try:
        with get_db().cursor(DictCursor) as cursor:
            auction = find_auction(cursor, auction_id)
            require_auction_manager(cursor, auction, session["user_id"])
            if auction["status"] != "closed":
                abort(400, description="This auction is still open.")
            if auction["winner_user_id"] is None:
                abort(404, description="This auction has no winner.")

            cursor.execute(
                "SELECT line1, city, postal_code FROM addresses WHERE user_id = %s",
                (auction["winner_user_id"],),
            )
            address = cursor.fetchone()
            if address is None:
                abort(404, description="The winner has no delivery address.")
    except MySQLError:
        current_app.logger.exception("Could not load winner address")
        abort(503, description="The winner's address is temporarily unavailable.")

    response = make_response(render_template("bids/winner_address.html", auction=auction, address=address))
    response.headers["Cache-Control"] = "private, no-store"
    return response


@bp.get("/profile/<int:user_id>/address")
@login_required
def profile_address(user_id):
    try:
        with get_db().cursor(DictCursor) as cursor:
            cursor.execute(
                """
                SELECT users.id, users.username,
                       addresses.line1, addresses.city, addresses.postal_code
                FROM users JOIN addresses ON addresses.user_id = users.id
                WHERE users.id = %s
                """,
                (user_id,),
            )
            profile = cursor.fetchone()
            if profile is None:
                abort(404, description="Address not found.")
    except MySQLError:
        current_app.logger.exception("Could not load profile address")
        abort(503, description="The address is temporarily unavailable.")

    # Intentionally vulnerable: authentication is required, but ownership is not checked.
    response = make_response(render_template("bids/profile_address.html", profile=profile))
    response.headers["Cache-Control"] = "private, no-store"
    return response
