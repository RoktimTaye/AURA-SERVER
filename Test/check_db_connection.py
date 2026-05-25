import os
import urllib.parse as urlparse
from dotenv import load_dotenv
import psycopg2

def check_db():
    load_dotenv()
    url = os.getenv("DATABASE_URL")
    if not url:
        print("DATABASE_URL not found in environment.")
        return

    try:
        parsed = urlparse.urlparse(url)
        print(f"Scheme: {parsed.scheme}")
        print(f"Host: {parsed.hostname}")
        print(f"Port: {parsed.port}")
        print(f"Database: {parsed.path[1:]}")
        print(f"Username: {parsed.username}")
        
        # Check for SSL in query parameters
        params = urlparse.parse_qs(parsed.query)
        print(f"Query Parameters: {params}")
        
        # Attempt connection
        print("Attempting to connect...")
        conn = psycopg2.connect(url)
        print("Successfully connected to the database.")
        
        # Check SSL status
        with conn.cursor() as cur:
            cur.execute("SHOW ssl;")
            ssl_status = cur.fetchone()
            print(f"SSL Status (server-side): {ssl_status[0] if ssl_status else 'Unknown'}")
            
        conn.close()
    except Exception as e:
        print(f"Error connecting to the database: {e}")

if __name__ == "__main__":
    check_db()
