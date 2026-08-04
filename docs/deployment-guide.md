# Deployment guide

For local development, run Uvicorn on port 8000 and Vite on port 5173. Native backend execution is preferred for direct webcam access on Windows. Docker deployments must explicitly pass through a real camera device and must be able to resolve and reach the physical ESP32-S3.

Production recommendations include PostgreSQL, HTTPS/WSS through a reverse proxy, authenticated/operator roles, a private IoT VLAN, explicit CORS origins, secrets outside source control, supervised processes, database backups, log rotation, and signed firmware updates. Do not expose the ESP32 REST API directly to the public internet.
