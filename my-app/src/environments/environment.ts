// Dev: points at the local Flask backend (`flask --app app run`).
// No API keys live in the frontend anymore — all external calls are server-side.
// Port 8000 (not 5000 — macOS AirPlay Receiver occupies 5000).
// Run the backend with: flask --app app run --port 8000
export const environment = {
  apiBaseUrl: 'https://za34t43kk6.execute-api.us-east-1.amazonaws.com/',
};
