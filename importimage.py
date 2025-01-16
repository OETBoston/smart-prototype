import requests
import os
from datetime import datetime
from requests.auth import HTTPBasicAuth

def get_panorama_image(username, password, api_key, lat, lon, width=1024, height=768, hfov=90):
    """
    Fetch a panorama image from Cyclomedia for a specific location in Boston.
    
    Args:
        username (str): Cyclomedia account username
        password (str): Cyclomedia account password
        api_key (str): Your Cyclomedia API key
        lat (float): Latitude in degrees
        lon (float): Longitude in degrees
        width (int): Desired image width in pixels
        height (int): Desired image height in pixels
        hfov (float): Horizontal field of view in degrees
    
    Returns:
        bytes: Image data if successful
        None: If request fails
    """
    # Base URL for the API
    base_url = "https://atlasapi.cyclomedia.com/api/panoramarendering"
    
    # We'll use EPSG:4326 (WGS84) for lat/lon coordinates
    endpoint = f"{base_url}/RenderByLocation2D/4326/{lon}/{lat}/"
    
    # Parameters for the request
    params = {
        "apiKey": api_key,
        "width": width,
        "height": height,
        "hfov": hfov
    }
    
    try:
        # Make the request with basic authentication
        response = requests.get(
            endpoint, 
            params=params,
            auth=HTTPBasicAuth(username, password)
        )
        
        # Check if request was successful
        if response.status_code == 200:
            return response.content
        elif response.status_code == 401:
            print("Authentication failed. Please check your username and password.")
            return None
        else:
            print(f"Error: {response.status_code}")
            print(response.text)
            return None
            
    except Exception as e:
        print(f"Request failed: {str(e)}")
        return None

def save_image(image_data, output_dir="output"):
    """
    Save the image data to a file with timestamp.
    
    Args:
        image_data (bytes): The image data to save
        output_dir (str): Directory to save the image in
    
    Returns:
        str: Path to saved image if successful
        None: If save fails
    """
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    # Generate filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"boston_panorama_{timestamp}.jpg"
    filepath = os.path.join(output_dir, filename)
    
    try:
        with open(filepath, 'wb') as f:
            f.write(image_data)
        return filepath
    except Exception as e:
        print(f"Failed to save image: {str(e)}")
        return None

def main():
    # Replace with your credentials
    USERNAME = "BostonAPI"
    PASSWORD = "KtPj!X(xz8W%dE*L"
    API_KEY = "ifcJSrsB2v4NyfIJ2XANerot-rUFG7g123slS3Eti7gx2PgxOTABKnwteD81GrgR"
    
    # Example coordinates for downtown Boston (near Boston Common)
    BOSTON_LAT = 42.3554
    BOSTON_LON = -71.0640
    
    # Fetch the image
    print("Fetching panorama image...")
    image_data = get_panorama_image(
        username=USERNAME,
        password=PASSWORD,
        api_key=API_KEY,
        lat=BOSTON_LAT,
        lon=BOSTON_LON
    )
    
    if image_data:
        # Save the image
        saved_path = save_image(image_data)
        if saved_path:
            print(f"Image saved successfully to: {saved_path}")
        else:
            print("Failed to save image")
    else:
        print("Failed to fetch image")

if __name__ == "__main__":
    main()