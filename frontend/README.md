# CampusCore – Frontend

Angular frontend for the CampusCore Resource Reservation and Check-in System.

This frontend is developed using Angular 21, TypeScript, HTML, and CSS. It communicates with the FastAPI backend through REST API endpoints.

## Iteration 1 – Implemented Features

- User login with backend authentication
- Session restoration and logout
- Role-based access for Student and Staff
- Resource listing from the backend
- Resource details, including location, capacity, description, and opening hours
- Loading and error handling

The frontend uses real backend data rather than mock resource data for the main resource browsing flow.

## Technology Stack

- Angular 21
- TypeScript
- HTML and CSS
- FastAPI REST API
- PostgreSQL (through the backend)

## Project Structure

The team repository contains:

- `backend/` – FastAPI backend
- `frontend/` – Angular frontend

## Requirements

Install the following before running the project:

- Node.js and npm
- Python and the backend dependencies
- Docker Desktop with PostgreSQL

## How to Run

### 1. Start PostgreSQL

Start the existing database container using Docker Desktop.

### 2. Start FastAPI

Open a terminal in the `backend` directory.

Activate the configured Python virtual environment and run:

```bash
python -m uvicorn app.main:app --reload
```

The API should be available at:

`http://127.0.0.1:8000`

### 3. Install Frontend Dependencies

Open another terminal in the `frontend` directory and run:

```bash
npm ci
```

### 4. Start Angular

```bash
npm start
```

Open:

`http://localhost:4200/login`

The Angular development server uses `proxy.conf.json` to forward API requests to the local FastAPI server.

## Build

To check that the frontend compiles successfully:

```bash
npm run build
```

## Testing

The Iteration 1 flow includes:

1. Log in with an existing Student or Staff account.
2. View the resource dashboard.
3. Select a resource.
4. View its details and opening hours.
5. Return to the resource dashboard.
6. Log out.

Test accounts and database setup should follow the team's backend documentation.

## Current Scope

This branch contains Iteration 1 functionality.

Reservation creation, reservation history, cancellation, QR check-in, and Admin management interfaces are planned for later iterations and are not included in this version.

Admin authentication is supported by the backend, but the Iteration 1 frontend does not provide Admin management pages.

## Notes

- FastAPI and PostgreSQL must be running for authenticated resource browsing.
- Local configuration files, dependencies, and generated build output are excluded from Git.
- The frontend should be tested together with the backend before merging into the main branch.
