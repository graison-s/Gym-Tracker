# Lift Log

A private, mobile-friendly Streamlit workout journal based on the supplied Gym Tracker UI. It supports a four-day weekly goal, rotating Push/Pull/Legs suggestions, completed workout entries, weekly body measurements, and Today/Week/Month/Year views.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Local development stores data in `lift_log.db` beside the app.

## Deploy to Streamlit Community Cloud

1. Push this folder to a private GitHub repository.
2. In Streamlit Community Cloud, create an app with `app.py` as the entry point.
3. Add `APP_USERNAME` and `APP_PASSWORD` under **Advanced settings > Secrets**. Do not use the example default credentials.
4. For persistent cloud data, create a hosted Postgres database (for example Supabase, Neon, or Railway) and add its connection string as `DATABASE_URL` in Secrets.

Without `DATABASE_URL`, the app runs with SQLite, which is useful locally but is not durable storage on Streamlit Community Cloud.
