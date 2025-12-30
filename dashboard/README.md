# WhatsApp LLM Dashboard

A FastAPI-based dashboard for viewing WhatsApp LLM data.

## Features

- **Tabbed Interface**: Navigate between Groups, Senders, Reactions, Messages, KB Topics, and KB Topic Messages
- **Pagination**: View data with customizable page sizes (10, 20, 50, 100 rows per page)
- **Basic Authentication**: Secured with HTTP Basic Auth using credentials from `.env` file
- **Responsive Design**: Clean, modern UI that works on desktop and mobile

## Usage

### Running with Docker Compose

The dashboard is automatically started with the rest of the services:

```bash
docker-compose up -d
```

Access the dashboard at: http://localhost:8080

### Authentication

The dashboard uses HTTP Basic Authentication with credentials from the `.env` file:
- Username: `WHATSAPP_BASIC_AUTH_USER`
- Password: `WHATSAPP_BASIC_AUTH_PASSWORD`

### Running Standalone

To run the dashboard separately:

```bash
cd dashboard
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8080
```

## Configuration

The dashboard requires the following environment variables (configured in `.env`):

- `DB_URI`: PostgreSQL connection string
- `WHATSAPP_BASIC_AUTH_USER`: Username for authentication
- `WHATSAPP_BASIC_AUTH_PASSWORD`: Password for authentication

## Architecture

- **Backend**: FastAPI with async SQLModel for database queries
- **Frontend**: Jinja2 templates with embedded CSS
- **Database**: PostgreSQL accessed via the main application's models
- **Authentication**: HTTP Basic Auth

## Tabs

1. **Groups**: View WhatsApp groups with management settings
2. **Senders**: View all message senders
3. **Reactions**: View emoji reactions to messages
4. **Messages**: View all messages with text and media
5. **KB Topics**: View knowledge base topics extracted from conversations
6. **KB Topic Messages**: View relationships between topics and messages
