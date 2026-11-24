# Student Auctions API contract

## Διαθέσιμο στον κοινό κορμό

| Μέθοδος | Διαδρομή | Απόκριση |
| --- | --- | --- |
| GET | `/health` | `200 {"status":"ok"}` όταν πετυχαίνει το `SELECT 1` στη MariaDB. `503 {"status":"unavailable"}` όταν αποτυγχάνει ο έλεγχος. |

## Προγραμματισμένες διαδρομές των modules

Τα Blueprints `auth`, `auctions`, `bids` και `profiles` είναι καταχωρισμένα χωρίς URL prefix. Οι παρακάτω διαδρομές θα προστεθούν από τους υπευθύνους τους.

| Blueprint | Μέθοδος | Διαδρομή | Λειτουργία |
| --- | --- | --- | --- |
| `auth` | GET, POST | `/register` | Εγγραφή φοιτητή. Το POST δέχεται `student_id`, `username`, `email`, `password`. |
| `auth` | GET, POST | `/login` | Σύνδεση. Το POST δέχεται `username`, `password`. |
| `auth` | POST | `/logout` | Αποσύνδεση |
| `auth` | GET | `/me` | Στοιχεία του συνδεδεμένου χρήστη χωρίς το hash του κωδικού |
| `auctions` | GET | `/auctions` | Λίστα και αναζήτηση με `?q=` |
| `auctions` | GET | `/auctions/new` | Φόρμα νέας δημοπρασίας |
| `auctions` | POST | `/auctions` | Δημιουργία δημοπρασίας με `title`, `description`, `starting_price`, `ends_at`. |
| `auctions` | GET | `/auctions/<id>` | Λεπτομέρειες δημοπρασίας |
| `auctions` | GET, POST | `/auctions/<id>/edit` | Επεξεργασία από πωλητή ή admin |
| `bids` | GET, POST | `/auctions/<id>/bids` | Λίστα προσφορών. Το POST δέχεται `amount`. |
| `bids` | POST | `/auctions/<id>/close` | Κλείσιμο δημοπρασίας από τον πωλητή και επιλογή νικητή |
| `bids` | GET | `/auctions/<id>/winner-address` | Διεύθυνση νικητή για τον εξουσιοδοτημένο πωλητή ή admin |
| `bids` | GET | `/profile/<user_id>/address` | Πρόσβαση στη διεύθυνση με έλεγχο ταυτότητας χρήστη ή ρόλου admin |
| `profiles` | GET | `/settings` | Φόρμα της τρέχουσας διεύθυνσης |
| `profiles` | POST | `/settings/address` | Ενημέρωση διεύθυνσης με `line1`, `city`, `postal_code`. |
| `profiles` | GET | `/admin` | Πίνακας διαχείρισης |
| `profiles` | GET | `/admin/addresses` | Λίστα διευθύνσεων για admin |

## Session και δικαιώματα

- Το Auth αποθηκεύει το `users.id` ως ακέραιο στο `session["user_id"]` μετά τη σύνδεση και εκτελεί `session.clear()` στην αποσύνδεση.
- Για προστατευμένες HTML σελίδες, το `app.core.security.login_required` ανακατευθύνει στο `/login` με HTTP `302` όταν λείπει το `user_id`. Το Auth θα προσθέσει τη διαδρομή `/login`.
- Τα προστατευμένα API endpoints επιστρέφουν `401` όταν λείπει η ταυτοποίηση. Κάθε module κάνει τους δικούς του ελέγχους ρόλου και πρόσβασης στην αντίστοιχη εγγραφή. Επιστρέφει `403` για έλλειψη δικαιώματος, `404` για ανύπαρκτη εγγραφή και `400` για μη έγκυρα δεδομένα.
- Για τα κοινά helpers χρησιμοποιούμε τα imports `from app.core.security import login_required` και `from app.core.database import get_db`.

## MariaDB

- Το [`db/schema.sql`](../db/schema.sql) ορίζει το κοινό schema. Το `app.core.database.get_db()` ανοίγει τη σύνδεση όταν χρειαστεί και την επαναχρησιμοποιεί στο ίδιο request. Το Flask κλείνει τη σύνδεση στο teardown του application context.
- Χρησιμοποιούμε UTC και παραμετροποιημένα queries με placeholders `%s`. Το module που γράφει δεδομένα χειρίζεται το `commit()` και το `rollback()` της συναλλαγής του.
- Το Auctions διαχειρίζεται τα πεδία καταχώρισης `seller_id`, `title`, `description`, `starting_price`, `is_public` και `ends_at`. Το `id` και το `created_at` έχουν αυτόματες τιμές από τη βάση.
- Το Bids διαχειρίζεται τον πίνακα `bids` και τα πεδία `auctions.status` και `auctions.winner_user_id`. Οι νέες δημοπρασίες παίρνουν από το schema `status='open'` και `winner_user_id=NULL`.
