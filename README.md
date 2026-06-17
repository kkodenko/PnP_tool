# Price & Promo Simulator — Streamlit + Google Sheets

This app reads and writes data from Google Sheets.

## Google Sheet ID

```text
1eUa3UNl6WbQAgx59caB-GSYaKUSPcniqA7Evvo1BJbs
```

## Required Google Sheet tabs

```text
config
coefficients
aggregation_matrix
base_price_scenarios
promo_scenarios
```

## Local run

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Google credentials

For local testing, create:

```text
.streamlit/secrets.toml
```

A placeholder file is included, but you must replace all placeholder values with the real Google Service Account JSON values.

Do **not** push `.streamlit/secrets.toml` to GitHub.

For Streamlit Cloud, paste the same TOML content into:

```text
App → Settings → Secrets
```

## Give Google Sheet access

Share your Google Sheet with the service account email:

```text
client_email from secrets.toml
```

Access level:

```text
Editor
```

## GitHub files to commit

Commit:

```text
app.py
requirements.txt
README.md
.gitignore
.streamlit/secrets.toml.example
```

Do not commit:

```text
.streamlit/secrets.toml
```
