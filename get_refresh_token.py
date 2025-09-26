#!/usr/bin/env python3
"""
Helper script to get Spotify refresh token for the pin manager.
Run this once to get your refresh token, then use it in the main script.
"""

import os
import webbrowser
import urllib.parse
import urllib.request
import json

def get_refresh_token():
    client_id = input("Enter your Spotify CLIENT_ID: ").strip()
    client_secret = input("Enter your Spotify CLIENT_SECRET: ").strip()
    
    # Step 1: Get authorization code
    auth_url = "https://accounts.spotify.com/authorize"
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": "http://localhost:8888/callback",
        "scope": "playlist-modify-public playlist-modify-private playlist-read-private playlist-read-collaborative"
    }
    
    auth_url_with_params = auth_url + "?" + urllib.parse.urlencode(params)
    print(f"\n🔗 Please go to this URL in your browser:")
    print(f"{auth_url_with_params}")
    print(f"\n📋 After clicking 'Agree', you'll be redirected to a URL that looks like:")
    print(f"http://localhost:8888/callback?code=AQB...")
    print(f"\n📝 Copy the ENTIRE 'code' parameter value (everything after 'code=')")
    print(f"   and paste it here:")
    
    webbrowser.open(auth_url_with_params)
    
    auth_code = input("Authorization code: ").strip()
    
    # Step 2: Exchange code for tokens
    token_url = "https://accounts.spotify.com/api/token"
    data = {
        "grant_type": "authorization_code",
        "code": auth_code,
        "redirect_uri": "http://localhost:8888/callback",
        "client_id": client_id,
        "client_secret": client_secret
    }
    
    req = urllib.request.Request(token_url, data=urllib.parse.urlencode(data).encode())
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    
    try:
        with urllib.request.urlopen(req) as response:
            response_data = response.read().decode()
            token_data = json.loads(response_data)
            
        print("\n✅ Success! Here are your tokens:")
        print(f"ACCESS_TOKEN: {token_data['access_token']}")
        print(f"REFRESH_TOKEN: {token_data['refresh_token']}")
        print(f"EXPIRES_IN: {token_data['expires_in']} seconds")
        
        print(f"\nSet these environment variables:")
        print(f"$env:SPOTIFY_CLIENT_ID=\"{client_id}\"")
        print(f"$env:SPOTIFY_CLIENT_SECRET=\"{client_secret}\"")
        print(f"$env:SPOTIFY_REFRESH_TOKEN=\"{token_data['refresh_token']}\"")
        
    except urllib.error.HTTPError as e:
        error_response = e.read().decode()
        print(f"❌ HTTP Error {e.code}: {error_response}")
        print(f"Request data: {data}")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    get_refresh_token()
