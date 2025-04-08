import os
import time
import datetime
import pytz
import pandas as pd
import numpy as np
import requests
import yfinance as yf
import plotly.graph_objects as go
import plotly.express as px
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import telebot
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

"""
Before running this script, install required packages with:
pip install fastapi uvicorn pandas numpy yfinance plotly pytz telebot apscheduler Jinja2
"""

# Configuration
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "YOUR_TELEGRAM_CHAT_ID")
DEBUG = os.environ.get("DEBUG", "False").lower() == "true"
NIFTY50_TICKER = "^NSEI"  # Yahoo Finance ticker for Nifty 50

# Initialize FastAPI app
app = FastAPI()
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# Initialize Telegram bot
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

# Create necessary directories
os.makedirs("static", exist_ok=True)
os.makedirs("templates", exist_ok=True)

# Create HTML template
with open("templates/index.html", "w") as f:
    f.write("""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Nifty50 Trading Bot</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body {
            padding-top: 50px;
            background-color: #f8f9fa;
        }
        .card {
            box-shadow: 0 4px 8px rgba(0,0,0,0.1);
            margin-bottom: 20px;
        }
        .buy {
            color: green;
            font-weight: bold;
        }
        .sell {
            color: red;
            font-weight: bold;
        }
        .neutral {
            color: orange;
            font-weight: bold;
        }
        .header {
            background-color: #052c65;
            color: white;
            padding: 20px 0;
            margin-bottom: 30px;
        }
        .last-updated {
            font-style: italic;
            font-size: 0.9rem;
            color: #6c757d;
        }
    </style>
</head>
<body>
    <div class="header text-center">
        <h1>Nifty50 Trading Bot</h1>
        <p>RSI-based analysis and recommendations</p>
    </div>
    <div class="container">
        <div class="row">
            <div class="col-md-12">
                <div class="card">
                    <div class="card-header bg-primary text-white">
                        <h2>Market Overview</h2>
                    </div>
                    <div class="card-body">
                        <p class="last-updated">Last updated: {{ last_updated }}</p>
                        <h3>Current Nifty50: {{ current_price }} ({{ price_change }}%)</h3>
                        <div class="row mt-4">
                            <div class="col-md-4">
                                <div class="card">
                                    <div class="card-header">Daily RSI</div>
                                    <div class="card-body text-center">
                                        <h3>{{ daily_rsi }}</h3>
                                        <p class="{{ daily_signal_class }}">{{ daily_signal }}</p>
                                    </div>
                                </div>
                            </div>
                            <div class="col-md-4">
                                <div class="card">
                                    <div class="card-header">Weekly RSI</div>
                                    <div class="card-body text-center">
                                        <h3>{{ weekly_rsi }}</h3>
                                        <p class="{{ weekly_signal_class }}">{{ weekly_signal }}</p>
                                    </div>
                                </div>
                            </div>
                            <div class="col-md-4">
                                <div class="card">
                                    <div class="card-header">Monthly RSI</div>
                                    <div class="card-body text-center">
                                        <h3>{{ monthly_rsi }}</h3>
                                        <p class="{{ monthly_signal_class }}">{{ monthly_signal }}</p>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
                
                <div class="card">
                    <div class="card-header bg-success text-white">
                        <h2>Overall Recommendation</h2>
                    </div>
                    <div class="card-body text-center">
                        <h3 class="{{ overall_signal_class }}">{{ overall_signal }}</h3>
                        <p>{{ recommendation_reason }}</p>
                    </div>
                </div>
                
                <div class="card">
                    <div class="card-header bg-info text-white">
                        <h2>Nifty50 Price Chart</h2>
                    </div>
                    <div class="card-body">
                        <img src="/static/price_chart.png" class="img-fluid" alt="Nifty50 Price Chart">
                    </div>
                </div>
                
                <div class="card">
                    <div class="card-header bg-info text-white">
                        <h2>RSI Charts</h2>
                    </div>
                    <div class="card-body">
                        <img src="/static/rsi_chart.png" class="img-fluid" alt="RSI Charts">
                    </div>
                </div>
            </div>
        </div>
    </div>
    <footer class="text-center p-4 mt-4">
        <p>&copy; 2025 Nifty50 Trading Bot | Data refreshes every 15 minutes during market hours</p>
    </footer>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
    """)

# Global variables to store the latest data
latest_data = {
    "last_updated": "Not updated yet",
    "current_price": 0,
    "price_change": 0,
    "daily_rsi": 0,
    "weekly_rsi": 0,
    "monthly_rsi": 0,
    "daily_signal": "Neutral",
    "weekly_signal": "Neutral",
    "monthly_signal": "Neutral",
    "daily_signal_class": "neutral",
    "weekly_signal_class": "neutral",
    "monthly_signal_class": "neutral",
    "overall_signal": "Neutral",
    "overall_signal_class": "neutral",
    "recommendation_reason": "Waiting for first analysis",
}

def calculate_rsi(data, window=14):
    """
    Calculate RSI for given data with proper handling of NaN values.
    
    Args:
        data: pandas Series of price data
        window: RSI calculation period
        
    Returns:
        pandas Series of RSI values
    """
    # Handle missing values first
    data = data.fillna(method='ffill')  # Forward fill missing values
    
    delta = data.diff()
    
    # Create positive and negative change Series
    up_values = np.where(delta > 0, delta, 0)
    down_values = np.where(delta < 0, -delta, 0)
    
    # Convert to pandas Series
    up = pd.Series(up_values)
    down = pd.Series(down_values)
    
    # Calculate the rolling average of up and down values
    avg_up = up.rolling(window=window, min_periods=1).mean()
    avg_down = down.rolling(window=window, min_periods=1).mean()
    
    # Avoid division by zero
    avg_down = np.where(avg_down == 0, 0.0001, avg_down)
    
    # Calculate RS value
    rs = avg_up / avg_down
    
    # Calculate RSI
    rsi = 100 - (100 / (1 + rs))
    
    # Handle edge cases
    rsi = np.where(avg_down == 0.0001, 100, rsi)  # If all down movements are 0, RSI is 100
    rsi = np.where(np.isnan(rsi), 50, rsi)  # Replace any remaining NaN with neutral 50
    
    return pd.Series(rsi, index=data.index)

def get_rsi_signal(rsi_value):
    """Determine buy/sell signal based on RSI value."""
    # Handle potential NaN value
    if np.isnan(rsi_value):
        return "Neutral", "neutral"
        
    if rsi_value < 30:
        return "Buy", "buy"
    elif rsi_value > 70:
        return "Sell", "sell"
    else:
        return "Neutral", "neutral"

def get_overall_signal(daily_rsi, weekly_rsi, monthly_rsi):
    """Calculate overall signal based on all timeframes."""
    # Handle potential NaN values
    daily_rsi = 50 if np.isnan(daily_rsi) else daily_rsi
    weekly_rsi = 50 if np.isnan(weekly_rsi) else weekly_rsi
    monthly_rsi = 50 if np.isnan(monthly_rsi) else monthly_rsi
    
    # Convert RSI levels to numeric scores
    # -1 for sell, 0 for neutral, 1 for buy
    daily_score = -1 if daily_rsi > 70 else (1 if daily_rsi < 30 else 0)
    weekly_score = -1 if weekly_rsi > 70 else (1 if weekly_rsi < 30 else 0)
    monthly_score = -1 if monthly_rsi > 70 else (1 if monthly_rsi < 30 else 0)
    
    # Weight the timeframes (daily has highest weight, monthly lowest)
    total_score = daily_score * 0.5 + weekly_score * 0.3 + monthly_score * 0.2
    
    reason = ""
    if total_score > 0.3:
        signal = "Strong Buy"
        signal_class = "buy"
        reason = "Most timeframes show oversold conditions."
    elif total_score > 0:
        signal = "Buy"
        signal_class = "buy"
        reason = "RSI suggests bullish momentum building."
    elif total_score < -0.3:
        signal = "Strong Sell"
        signal_class = "sell"
        reason = "Most timeframes show overbought conditions."
    elif total_score < 0:
        signal = "Sell"
        signal_class = "sell"
        reason = "RSI suggests bearish momentum building."
    else:
        signal = "Neutral"
        signal_class = "neutral"
        reason = "Conflicting signals across timeframes. Consider waiting."
    
    # Add specific reasoning based on different timeframes
    timeframe_details = []
    if daily_score == 1:
        timeframe_details.append("Daily RSI indicates oversold conditions")
    elif daily_score == -1:
        timeframe_details.append("Daily RSI indicates overbought conditions")
        
    if weekly_score == 1:
        timeframe_details.append("Weekly RSI indicates oversold conditions")
    elif weekly_score == -1:
        timeframe_details.append("Weekly RSI indicates overbought conditions")
        
    if monthly_score == 1:
        timeframe_details.append("Monthly RSI indicates oversold conditions")
    elif monthly_score == -1:
        timeframe_details.append("Monthly RSI indicates overbought conditions")
    
    if timeframe_details:
        reason += " " + ", ".join(timeframe_details) + "."
    
    return signal, signal_class, reason

def generate_charts(daily_data, weekly_data, monthly_data):
    """Generate price and RSI charts."""
    # Price chart
    fig_price = go.Figure()
    
    # Handle potential NaN values in data
    daily_data = daily_data.fillna(method='ffill')
    
    fig_price.add_trace(go.Candlestick(
        x=daily_data.index,
        open=daily_data['Open'],
        high=daily_data['High'],
        low=daily_data['Low'],
        close=daily_data['Close'],
        name='Price'
    ))
    fig_price.update_layout(
        title='Nifty50 Price Chart (Last 90 Days)',
        xaxis_title='Date',
        yaxis_title='Price',
        template='plotly_white',
        height=600
    )
    fig_price.write_image("static/price_chart.png")
    
    # RSI charts
    fig_rsi = go.Figure()
    
    # Daily RSI
    daily_rsi = calculate_rsi(daily_data['Close'])
    fig_rsi.add_trace(go.Scatter(
        x=daily_data.index[-30:],
        y=daily_rsi[-30:],
        mode='lines',
        name='Daily RSI'
    ))
    
    # Weekly RSI
    weekly_data = weekly_data.fillna(method='ffill')
    weekly_rsi = calculate_rsi(weekly_data['Close'])
    weekly_dates = []
    weekly_rsi_values = []
    for date, rsi_val in zip(weekly_data.index[-10:], weekly_rsi[-10:]):
        if np.isnan(rsi_val):
            continue  # Skip NaN values
        for i in range(5):  # Expand weekly data to daily for visualization
            if len(weekly_dates) < 30:  # Limit to 30 days
                weekly_dates.append(date + datetime.timedelta(days=i))
                weekly_rsi_values.append(rsi_val)
    
    fig_rsi.add_trace(go.Scatter(
        x=weekly_dates,
        y=weekly_rsi_values,
        mode='lines',
        name='Weekly RSI',
        line=dict(dash='dash')
    ))
    
    # Monthly RSI
    monthly_data = monthly_data.fillna(method='ffill')
    monthly_rsi = calculate_rsi(monthly_data['Close'])
    monthly_dates = []
    monthly_rsi_values = []
    for date, rsi_val in zip(monthly_data.index[-5:], monthly_rsi[-5:]):
        if np.isnan(rsi_val):
            continue  # Skip NaN values
        for i in range(6):  # Expand monthly data to weekly for visualization
            if len(monthly_dates) < 30:  # Limit to 30 days
                monthly_dates.append(date + datetime.timedelta(days=i*5))
                monthly_rsi_values.append(rsi_val)
    
    fig_rsi.add_trace(go.Scatter(
        x=monthly_dates,
        y=monthly_rsi_values,
        mode='lines',
        name='Monthly RSI',
        line=dict(dash='dot')
    ))
    
    # Add horizontal lines for overbought/oversold levels
    fig_rsi.add_shape(
        type='line',
        y0=70, y1=70,
        x0=daily_data.index[-30], x1=daily_data.index[-1],
        line=dict(color='red', width=1, dash='dash'),
    )
    fig_rsi.add_shape(
        type='line',
        y0=30, y1=30,
        x0=daily_data.index[-30], x1=daily_data.index[-1],
        line=dict(color='green', width=1, dash='dash'),
    )
    
    fig_rsi.update_layout(
        title='RSI Analysis (Multiple Timeframes)',
        xaxis_title='Date',
        yaxis_title='RSI Value',
        template='plotly_white',
        height=500,
        yaxis=dict(range=[0, 100])
    )
    fig_rsi.write_image("static/rsi_chart.png")

def is_market_open():
    """Check if the Indian market is currently open."""
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.datetime.now(ist)
    
    # Market hours: 9:15 AM to 3:30 PM, Monday to Friday
    if now.weekday() >= 5:  # Weekend
        return False
    
    market_open = now.replace(hour=9, minute=15, second=0)
    market_close = now.replace(hour=15, minute=30, second=0)
    
    return market_open <= now <= market_close

def send_telegram_message(message):
    """Send message to Telegram."""
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message, parse_mode='Markdown')
        return True
    except Exception as e:
        print(f"Error sending Telegram message: {e}")
        return False

def safe_get_value(series, index=-1, default=50.0):
    """Safely get a value from a pandas Series with error handling."""
    try:
        value = series.iloc[index]
        return default if np.isnan(value) else value
    except (IndexError, KeyError, AttributeError):
        return default

def generate_daily_summary(daily_data, weekly_data, monthly_data):
    """Generate end-of-day summary report with NaN handling."""
    # Calculate RSI values with NaN handling
    daily_rsi_series = calculate_rsi(daily_data['Close'])
    weekly_rsi_series = calculate_rsi(weekly_data['Close'])
    monthly_rsi_series = calculate_rsi(monthly_data['Close'])
    
    daily_rsi_value = safe_get_value(daily_rsi_series)
    weekly_rsi_value = safe_get_value(weekly_rsi_series)
    monthly_rsi_value = safe_get_value(monthly_rsi_series)
    
    # Get signals
    daily_signal, _ = get_rsi_signal(daily_rsi_value)
    weekly_signal, _ = get_rsi_signal(weekly_rsi_value)
    monthly_signal, _ = get_rsi_signal(monthly_rsi_value)
    
    # Get overall signal
    overall_signal, _, recommendation_reason = get_overall_signal(
        daily_rsi_value, weekly_rsi_value, monthly_rsi_value
    )
    
    # Calculate price change with NaN handling
    try:
        current_price = safe_get_value(daily_data['Close'])
        prev_close = safe_get_value(daily_data['Close'], -2)
        price_change_pct = ((current_price - prev_close) / prev_close) * 100 if prev_close != 0 else 0
    except Exception:
        current_price = 0
        price_change_pct = 0
    
    # Format date with error handling
    try:
        date_str = daily_data.index[-1].strftime('%d %b %Y')
    except (IndexError, AttributeError):
        date_str = datetime.datetime.now().strftime('%d %b %Y')
    
    # Generate summary message
    message = f"""
*Nifty50 Daily Summary: {date_str}*

*Closing Price:* {current_price:.2f} ({price_change_pct:.2f}%)

*RSI Analysis:*
• Daily RSI: {daily_rsi_value:.2f} - {daily_signal}
• Weekly RSI: {weekly_rsi_value:.2f} - {weekly_signal}
• Monthly RSI: {monthly_rsi_value:.2f} - {monthly_signal}

*Overall Recommendation: {overall_signal}*
{recommendation_reason}

Next update will be available after market open tomorrow.
"""
    return message

def update_data():
    """Update stock data and analysis with robust error handling."""
    global latest_data
    
    try:
        # Download data
        end_date = datetime.datetime.now()
        start_date = end_date - datetime.timedelta(days=365)
        
        try:
            daily_data = yf.download(NIFTY50_TICKER, start=start_date, end=end_date, interval="1d")
            if daily_data.empty:
                print("No daily data available, using cached data if available")
                raise ValueError("Empty daily data")
                
            weekly_data = yf.download(NIFTY50_TICKER, start=start_date, end=end_date, interval="1wk")
            if weekly_data.empty:
                print("No weekly data available, using cached data if available")
                raise ValueError("Empty weekly data")
                
            monthly_data = yf.download(NIFTY50_TICKER, start=start_date - datetime.timedelta(days=365*2), end=end_date, interval="1mo")
            if monthly_data.empty:
                print("No monthly data available, using cached data if available")
                raise ValueError("Empty monthly data")
                
        except Exception as e:
            print(f"Error downloading data: {e}")
            # Return early if we can't get fresh data and we don't have previous data
            if latest_data["last_updated"] == "Not updated yet":
                return False
                
            # Continue with cached data for visualization but don't update
            print("Using cached data for analysis")
            return True
        
        # Generate charts
        try:
            generate_charts(daily_data, weekly_data, monthly_data)
        except Exception as e:
            print(f"Error generating charts: {e}")
        
        # Calculate RSI values with NaN handling
        daily_rsi_series = calculate_rsi(daily_data['Close'])
        weekly_rsi_series = calculate_rsi(weekly_data['Close'])
        monthly_rsi_series = calculate_rsi(monthly_data['Close'])
        
        daily_rsi_value = safe_get_value(daily_rsi_series)
        weekly_rsi_value = safe_get_value(weekly_rsi_series)
        monthly_rsi_value = safe_get_value(monthly_rsi_series)
        
        # Get signals
        daily_signal, daily_signal_class = get_rsi_signal(daily_rsi_value)
        weekly_signal, weekly_signal_class = get_rsi_signal(weekly_rsi_value)
        monthly_signal, monthly_signal_class = get_rsi_signal(monthly_rsi_value)
        
        # Get overall signal
        overall_signal, overall_signal_class, recommendation_reason = get_overall_signal(
            daily_rsi_value, weekly_rsi_value, monthly_rsi_value
        )
        
        # Calculate price change with error handling
        try:
            current_price = safe_get_value(daily_data['Close'])
            prev_close = safe_get_value(daily_data['Close'], -2)
            price_change_pct = ((current_price - prev_close) / prev_close) * 100 if prev_close != 0 else 0
        except Exception:
            current_price = 0
            price_change_pct = 0
        
        # Update global data
        latest_data = {
            "last_updated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "current_price": f"{current_price:.2f}",
            "price_change": f"{price_change_pct:.2f}",
            "daily_rsi": f"{daily_rsi_value:.2f}",
            "weekly_rsi": f"{weekly_rsi_value:.2f}",
            "monthly_rsi": f"{monthly_rsi_value:.2f}",
            "daily_signal": daily_signal,
            "weekly_signal": weekly_signal,
            "monthly_signal": monthly_signal,
            "daily_signal_class": daily_signal_class,
            "weekly_signal_class": weekly_signal_class,
            "monthly_signal_class": monthly_signal_class,
            "overall_signal": overall_signal,
            "overall_signal_class": overall_signal_class,
            "recommendation_reason": recommendation_reason,
        }
        
        # Send telegram update if during market hours
        if is_market_open():
            message = f"""
*Nifty50 Update: {latest_data['last_updated']}*

*Current Price:* {latest_data['current_price']} ({latest_data['price_change']}%)

*RSI Analysis:*
• Daily: {latest_data['daily_rsi']} - {latest_data['daily_signal']}
• Weekly: {latest_data['weekly_rsi']} - {latest_data['weekly_signal']}
• Monthly: {latest_data['monthly_rsi']} - {latest_data['monthly_signal']}

*Recommendation: {latest_data['overall_signal']}*
{latest_data['recommendation_reason']}
"""
            send_telegram_message(message)
        
        # Check if market just closed for the day
        ist = pytz.timezone('Asia/Kolkata')
        now = datetime.datetime.now(ist)
        if now.hour == 15 and now.minute >= 30 and now.minute < 45:
            # Send daily summary after market close
            summary_message = generate_daily_summary(daily_data, weekly_data, monthly_data)
            send_telegram_message(summary_message)
            
        return True
        
    except Exception as e:
        print(f"Error updating data: {e}")
        if DEBUG:
            import traceback
            traceback.print_exc()
        return False

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, **latest_data})

@app.get("/update")
async def force_update():
    success = update_data()
    return {"status": "success" if success else "error"}

def start_scheduler():
    scheduler = BackgroundScheduler()
    
    # Update data every 15 minutes during market hours
    scheduler.add_job(
        update_data,
        trigger=CronTrigger(day_of_week='mon-fri', hour='9-15', minute='*/15', timezone='Asia/Kolkata'),
        id='market_hours_update'
    )
    
    # Daily summary after market close
    scheduler.add_job(
        update_data,
        trigger=CronTrigger(day_of_week='mon-fri', hour=15, minute=35, timezone='Asia/Kolkata'),
        id='daily_summary'
    )
    
    # Initial update on startup
    scheduler.add_job(
        update_data,
        trigger='date',
        run_date=datetime.datetime.now() + datetime.timedelta(seconds=10),
        id='initial_update'
    )
    
    scheduler.start()
    print("Scheduler started!")

@app.on_event("startup")
async def startup_event():
    start_scheduler()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
