import requests

def get_bitcoin_price():
    try:
        # Construct the URL to fetch Bitcoin data from CoinGecko API
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
        
        # Send a GET request to the CoinGecko API
        response = requests.get(url)
        
        # Check if the request was successful
        if response.status_code == 200:
            # Parse the JSON response
            data = response.json()
            
            # Extract the Bitcoin price in USD
            bitcoin_price = data['bitcoin']['usd']
            
            # Print the Bitcoin price
            print(f"Current Bitcoin price in USD: ${bitcoin_price}")
        else:
            print(f"Failed to fetch data. Status code: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"An error occurred while fetching the data: {e}")

if __name__ == '__main__':
    get_bitcoin_price()