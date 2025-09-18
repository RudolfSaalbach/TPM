# Google Calendar API Setup Guide

## Overview
This guide helps you set up Google Calendar API integration for Chronos Engine.

## Prerequisites
- Google Cloud Platform account
- Python 3.11+ installed
- Chronos Engine project setup

## Step 1: Create Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing one
3. Name it something like "chronos-calendar-integration"

## Step 2: Enable Google Calendar API

1. In the Google Cloud Console, go to "APIs & Services" > "Library"
2. Search for "Google Calendar API"
3. Click on it and press "Enable"

## Step 3: Create OAuth 2.0 Credentials

1. Go to "APIs & Services" > "Credentials"
2. Click "Create Credentials" > "OAuth client ID"
3. Choose "Desktop application" as application type
4. Name it "Chronos Engine Desktop Client"
5. Download the JSON file

## Step 4: Configure Chronos Engine

1. Rename the downloaded file to `credentials.json`
2. Place it in the `config/` directory
3. Update your `.env` file:
   ```bash
   GOOGLE_CALENDAR_ENABLED=true
   GOOGLE_CREDENTIALS_FILE=config/credentials.json
   GOOGLE_TOKEN_FILE=config/token.json
   ```

## Step 5: First-Time Authorization

1. Run Chronos Engine:
   ```bash
   python -m src.main
   ```

2. On first calendar sync, you'll be prompted to authorize:
   - A browser window will open
   - Sign in to your Google account
   - Grant calendar permissions
   - The authorization token will be saved automatically

## Step 6: Verify Setup

1. Check the health endpoint:
   ```bash
   curl http://localhost:8080/health
   ```

2. Trigger a manual sync:
   ```bash
   curl -X POST http://localhost:8080/sync/calendar \
        -H "Content-Type: application/json" \
        -d '{"days_ahead": 7, "force_refresh": true}'
   ```

## Configuration Options

Edit `config/chronos.yaml` to customize:

```yaml
calendar:
  credentials_file: "config/credentials.json"
  token_file: "config/token.json"
  default_calendar_id: "primary"  # or specific calendar ID
  sync_interval_minutes: 5

api:
  google_calendar_enabled: true
```

## Troubleshooting

### Common Issues

**Error: "Credentials not found"**
- Ensure `credentials.json` is in the `config/` directory
- Check file permissions

**Error: "Token expired"**
- Delete `config/token.json`
- Restart Chronos Engine to re-authorize

**Error: "API not enabled"**
- Verify Google Calendar API is enabled in Google Cloud Console
- Check project billing is set up

**Error: "Quota exceeded"**
- Check API usage in Google Cloud Console
- Reduce sync frequency in configuration

### Getting Calendar IDs

To sync with specific calendars instead of "primary":

1. Use Google Calendar API Explorer:
   ```
   https://developers.google.com/calendar/api/v3/reference/calendarList/list
   ```

2. Or check the calendar URL in Google Calendar web interface

## Security Best Practices

1. **Never commit credentials.json to version control**
2. **Use environment variables for sensitive configuration**
3. **Regularly rotate OAuth tokens**
4. **Limit API scope to minimum required permissions**

## Development vs Production

### Development
- Use mock calendar service (default)
- Set `GOOGLE_CALENDAR_ENABLED=false` in `.env`

### Production
- Use real Google Calendar API
- Set `GOOGLE_CALENDAR_ENABLED=true` in `.env`
- Ensure proper OAuth setup

## Support

For additional help:
- Check `logs/chronos.log` for detailed error messages
- Visit [Google Calendar API Documentation](https://developers.google.com/calendar/api)
- Create an issue in the Chronos Engine repository