# 🔮 Smart Stock Market Weather Forecaster

A Streamlit dashboard that predicts stock market sentiment ("Hot" or "Cold") based on financial news headlines. This app serves as the frontend for the `news_headline_trading_heat_prediction` project, exposing both traditional Machine Learning and Deep Learning models to end users.

## 🌟 Features

### 1. Traditional Machine Learning (LinearSVC)

Uses Support Vector Classification trained on historical stock price movements.

* **Variations:** Choose between models trained on different volatility thresholds:
* `LinearSVC, stock price move > 1 STD`
* `LinearSVC, stock price move > 0.5 STD`
* `LinearSVC, stock price move > 0.2 STD`


* **Output:** Binary classification (Hot / Cold).

### 2. Deep Learning (FinBERT-tone)

Uses a fine-tuned `yiyanghkust/finbert-tone` model (BERT architecture) specifically adapted for financial sentiment analysis.

* **Input:** Headlines (and optional summaries).
* **Output:**
* **Aggregated Prediction:** "Hot" (if Rising + Falling probability > Cold probability) or "Cold".
* **Detailed Probabilities:** Visual breakdown of sentiment into **Cold**, **Hot (Rising)**, and **Hot (Falling)**.



## 🏗️ Architecture

The frontend communicates with two independently deployed Cloud Run APIs:

* **SVC API:** `[https://stockapi3linsvm-241812484319.europe-west1.run.app](https://stockapi3linsvm-241812484319.europe-west1.run.app)`
* **FinBERT API:** `[https://trading-heat-api-398091546603.europe-west1.run.app](https://trading-heat-api-398091546603.europe-west1.run.app)`

## 🚀 How to Run Locally

1. **Clone the repository** and navigate to the project folder.
2. **Install dependencies:**
`pip install streamlit requests pandas`
3. **Configure API URL:**
Create a `.streamlit/secrets.toml` file in your project root with your local or deployed API URL:
`API_URL = "http://localhost:8000"`
*(Or use the deployed Cloud Run URL for SVC)*
4. **Run the Streamlit app:**
`streamlit run app.py`
5. Open your browser and go to `http://localhost:8501`.

## 📊 Output Examples

* **SVC Model:** Returns a straightforward "It's going to be hot" or "It will be definitely cold" based on your selected volatility threshold.
* **FinBERT Model:** Returns a detailed probability distribution bar chart, allowing you to see *how* confident the model is and whether the "Hot" sentiment is driven by rising or falling price expectations.

---

*Built for the Wagon Bootcamp*
