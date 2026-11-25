
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from flask import (
    Blueprint,
    abort,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from pymysql import MySQLError, ProgrammingError
from pymysql.cursors import DictCursor

from app.core.database import get_db
from app.core.security import login_required


bp = Blueprint("auctions", __name__, template_folder="templates")


@bp.get("/auctions")
def list_auctions():
    q = request.args.get("q", "").strip()
    sql = (
        "SELECT id, title, starting_price, status, ends_at "
        "FROM auctions WHERE is_public = TRUE"
    )
    if q:
        # INTENTIONALLY VULNERABLE: local CSE423 SQL injection demonstration.
        # Preserve the vulnerable snapshot before replacing this with parameters.
        sql += " AND title LIKE '%" + q + "%'"
    sql += " ORDER BY created_at DESC, id DESC"

    try:
        with get_db().cursor(DictCursor) as cursor:
            cursor.execute(sql)
            auctions = cursor.fetchall()
    except ProgrammingError as error:
        # Malformed demo input must not expose SQL or a database traceback.
        if error.args[0] != 1064:
            raise
        return render_template(
            "auctions/list.html",
            auctions=[],
            q=q,
            error="The search could not be processed. Please change your search.",
        ), 400

    return render_template("auctions/list.html", auctions=auctions, q=q)


@bp.get("/auctions/new")
@login_required
def new_auction():
    return render_template("auctions/new.html", form={})


def create_error(message):
    return render_template(
        "auctions/new.html",
        error=message,
        form=request.form,
    ), 400


@bp.post("/auctions")
@login_required
def create_auction():
    connection = get_db()
    user_id = session["user_id"]

    # Confirm that the session belongs to an active user.
    with connection.cursor(DictCursor) as cursor:
        cursor.execute(
            "SELECT id FROM users WHERE id = %s AND is_active = TRUE",
            (user_id,),
        )
        user = cursor.fetchone()

    if user is None:
        abort(403)

    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    price_text = request.form.get("starting_price", "").strip()
    ends_text = request.form.get("ends_at", "").strip()
    is_public_value = request.form.get("is_public")

    # Validate title and description.
    if not title or len(title) > 120:
        return create_error("Title must contain 1 to 120 characters.")

    if not description or len(description) > 10000:
        return create_error("Description must contain 1 to 10000 characters.")

    # Validate price using Decimal instead of float.
    try:
        starting_price = Decimal(price_text)
    except (InvalidOperation, ValueError):
        return create_error("Enter a valid starting price.")

    if (
        not starting_price.is_finite()
        or starting_price < Decimal("0")
        or starting_price > Decimal("99999999.99")
        or starting_price.as_tuple().exponent < -2
    ):
        return create_error(
            "Price must be between 0 and 99999999.99 EUR, "
            "with up to two decimal places."
        )

    # The datetime-local form sends a UTC date/time without timezone.
    try:
        ends_at = datetime.strptime(ends_text, "%Y-%m-%dT%H:%M")
    except ValueError:
        return create_error("Enter a valid end date and time.")

    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)

    if ends_at <= now_utc:
        return create_error("End date must be in the future (UTC).")

    # Missing checkbox means private auction.
    if is_public_value not in (None, "1"):
        return create_error("Invalid visibility selection.")

    is_public = 1 if is_public_value == "1" else 0

    # Only the Auctions module's fields are written.
    # Status and winner are managed by Branch_C.
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO auctions
                    (seller_id, title, description,
                     starting_price, is_public, ends_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    user_id,
                    title,
                    description,
                    starting_price,
                    is_public,
                    ends_at,
                ),
            )
        connection.commit()
    except MySQLError:
        connection.rollback()
        raise

    # Details route will be implemented in the next stage.
    return redirect(url_for("auctions.list_auctions"))
