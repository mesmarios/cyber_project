# Student Auctions (CSE423)

Ο κοινός κορμός εκκινεί ένα Flask web service και μία MariaDB. Το μόνο λειτουργικό endpoint της εφαρμογής είναι το `GET /health`. Τα συμφωνημένα URLs, οι συμβάσεις για το session και η κατανομή των πεδίων περιγράφονται στο [API contract](contracts/api.md).

## Εκκίνηση από καθαρό clone

Από τη ρίζα του repository, με ενεργό Docker Engine και Docker Compose:

```sh
cp .env.example .env
openssl rand -hex 32
openssl rand -hex 32
```

Βάλε την πρώτη τιμή στο `FLASK_SECRET_KEY` και τη δεύτερη στο `SECURE_FLASK_SECRET_KEY` μέσα στο `.env`. Τα στοιχεία MariaDB του παραδείγματος προορίζονται για το τοπικό demo. Το Flask συνδέεται στο `db:3306` μέσα στο δίκτυο του Compose. Η MariaDB δεν δημοσιεύει θύρα στον host.

```sh
docker compose -p student-auctions-initial up --build -d --wait
docker compose -p student-auctions-initial ps
curl -i --retry 5 --retry-connrefused http://127.0.0.1:5000/health
```

Αναμένεται HTTP 200 με `{"status":"ok"}`. Αν αλλάξεις το `WEB_PORT` στο `.env`, χρησιμοποίησε τη νέα θύρα στο `curl`.

## Επιβεβαίωση του seed

```sh
docker compose -p student-auctions-initial exec -T db sh -ec '
  export MYSQL_PWD="$MARIADB_PASSWORD"
  exec mariadb --user="$MARIADB_USER" --database="$MARIADB_DATABASE" --execute="
    SELECT
      (SELECT COUNT(*) FROM students) AS students,
      (SELECT COUNT(*) FROM users) AS users,
      (SELECT COUNT(*) FROM addresses) AS addresses,
      (SELECT COUNT(*) FROM auctions) AS auctions,
      (SELECT COUNT(*) FROM bids) AS bids;"
'
```

Σε νέο volume με το υπάρχον seed, οι αναμενόμενες μετρήσεις είναι `7`, `4`, `3`, `3` και `1`, αντίστοιχα. Η MariaDB εκτελεί το `db/schema.sql` και το `db/seed.sql` κατά την αρχικοποίηση ενός κενού volume. Ένα υπάρχον volume κρατά τα δεδομένα του, επομένως αλλαγές στο seed δεν εφαρμόζονται αυτόματα. Για νέο έλεγχο του seed χρησιμοποίησε νέο Compose project name και ελεύθερη τοπική θύρα.

## Δοκιμή με τη βάση εκτός λειτουργίας

Χρησιμοποίησε νέο project για να μην επηρεάσεις την κανονική βάση. Η παρακάτω εκκίνηση χρησιμοποιεί τη θύρα 15000:

```sh
project="student-auctions-smoke-$(date +%s)"
export WEB_PORT=15000
docker compose -p "$project" up --build -d --wait
curl -i --retry 5 --retry-connrefused http://127.0.0.1:15000/health
docker compose -p "$project" stop db
curl -i http://127.0.0.1:15000/health
docker compose -p "$project" down
unset WEB_PORT
```

Ο πρώτος έλεγχος αναμένεται να επιστρέψει 200 και ο δεύτερος 503 με `{"status":"unavailable"}`. Το `down` διατηρεί το volume του δοκιμαστικού project.

## Δεύτερη, ανεξάρτητη εκκίνηση

Η δεύτερη εκκίνηση απαιτεί έκδοση του Docker Compose που υποστηρίζει το `!override` του `compose.secure.yaml`.

```sh
docker compose -p student-auctions-secure -f compose.yaml -f compose.secure.yaml up --build -d --wait
curl -i --retry 5 --retry-connrefused http://127.0.0.1:5001/health
```

Το δεύτερο project χρησιμοποιεί δικό του volume, ξεχωριστό Flask secret και όνομα cookie, και τη θύρα `SECURE_WEB_PORT` (5001 από προεπιλογή). Μπορεί να τρέχει παράλληλα με το πρώτο. Στο αρχικό στάδιο και τα δύο projects φορτώνουν το υπάρχον demo seed με SHA-1. Το χωριστό secure seed και οι αλλαγές του Auth για τη δεύτερη έκδοση εκκρεμούν. Το πλάνο της ομάδας προβλέπει να διατηρηθούν οι ίδιες demo εγγραφές και IDs στο μελλοντικό seed.

Για τερματισμό με διατήρηση των volumes:

```sh
docker compose -p student-auctions-initial down
docker compose -p student-auctions-secure -f compose.yaml -f compose.secure.yaml down
```
