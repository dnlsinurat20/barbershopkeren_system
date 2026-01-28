# **Barbershop Keren Management System 💈**

**"Stop cleaning data downstream. Start fixing it upstream."**

An end-to-end Booking & Point of Sales (POS) system engineered to solve data quality issues at the source. Built to digitize operations for a local MSME (Micro, Small, and Medium Enterprise), ensuring 100% data integrity for downstream analytics.

## **📖 The Context (Why I Built This)**

In a previous [**Data Audit Project**](https://www.linkedin.com/feed/update/urn:li:activity:7417272002664673280/), I analyzed ten months of historical data from this barbershop. The findings were critical: **Revenue stagnation wasn't a business failure; it was a data visibility failure.**

* **Problem:** Manual entry led to 2500% duplication in customer records (e.g., "Fatur" vs "Faturr").  
* **Problem:** Revenue leakage due to unrecorded discounts and service upgrades.  
* **The Solution:** Instead of building a cleaning pipeline, I architected a **Data Ingestion System** that enforces validation at the point of entry.

## **🏗️ System Architecture**

This application is built on a **Serverless Architecture** to minimize costs for the MSME owner while maintaining scalability.

* **Frontend:** [Streamlit](https://streamlit.io/) (Python) for a responsive, mobile-friendly UI.  
* **Backend Logic:** Python (Pandas) for complex pricing rules, anti-fraud validation, and profit-sharing algorithms.  
* **Database:** Google Sheets API (acting as a relational database).  
* **Middleware:** Google Apps Script (GAS) to handle image uploads and bypass Service Account storage quotas.  
* **Notifications:** WhatsApp API integration for automated e-receipts and daily financial reports.

## **🚀 Key Features & Engineering Logic**

### **1\. Smart Identity Resolution (CRM)**

To solve the "Dirty Data" crisis, the app uses WhatsApp numbers as Unique Primary Keys.

* **Logic:** When a number is entered, the system queries the database. If it exists, it auto-fills the customer's name. If not, it creates a new index.  
* **Result:** Zero duplicate customer records.

### **2\. Anti-Fraud Financial Logic**

Manual cashiers often manipulate transaction values. This system enforces strict accounting rules:

* **Gross vs. Net Separation:** Discounts are recorded as separate negative line items, not hidden in the total.  
* **Smart Service Detection:** If a customer pays more than the base price (e.g., Rp 85k instead of Rp 70k), the system automatically detects it as an "Upgrade" or "Add-on" based on pricing logic, ensuring accurate SKU tracking.

### **3\. Real-Time Owner Analytics**

Replaces manual SQL queries with an instant dashboard.

* **Metrics:** Tracks Total Heads, Gross Revenue, Net Profit, and Top Performing Stylist.  
* **Profit Sharing:** Automatically calculates the 42/53/5 commission split based on net profit.

### **4\. Automated Engagement**

* **e-Receipts:** Generates a PNG receipt on-the-fly using the Pillow library and sends it via WhatsApp.  
* **Daily Recap:** Sends a detailed financial summary to the stakeholders' WhatsApp group at closing time.

## **🛠️ Installation & Setup**

If you want to run this project locally, follow these steps:

### **Prerequisites**

* Python 3.9+  
* A Google Cloud Platform (GCP) project with Sheets & Drive API enabled.

### **1\. Clone the Repository**

git clone \[https://github.com/dnlsinurat20/barbershopkeren-system.git\](https://github.com/dnlsinurat20/barbershopkeren-system.git)  
cd barbershop-system

### **2\. Install Dependencies**

pip install \-r requirements.txt

### **3\. Configure Secrets (Crucial)**

*Note: For security reasons, the credentials.json file is NOT included in this repo.*

* Create a credentials.json file in the root directory using your own GCP Service Account key.  
* Create a .streamlit/secrets.toml file for environment variables.

### **4\. Run the App**

streamlit run app.py

## **📂 Project Structure**

barbershop-system/  
├── .streamlit/  
│   └── config.toml      \# Server configuration (Max upload size)  
├── app.py               \# Main application logic (Frontend & Backend)  
├── requirements.txt     \# Python dependencies  
├── logo\_struk.png       \# Asset for receipt generation  
├── google\_apps\_script.js \# Code used for Drive API middleware  
├── credentials.example.json \# Template for GCP credentials  
└── README.md            \# Documentation

## **🛡️ Security & Privacy Note**

This repository is a **portfolio version** of the live production app.

* All sensitive keys, passwords, and API tokens have been removed or replaced with placeholders.  
* Customer data shown in screenshots or demos is dummy data generated for demonstration purposes.

## **🤝 Connect**

This project represents my transition from **Data Analysis** to **Data Engineering**. I believe that good analysis starts with good data architecture.

* **LinkedIn:** https://www.linkedin.com/in/daniel-sinurat-509951397/?locale=in_ID
* **Portfolio:** https://www.linkedin.com/feed/update/urn:li:activity:7417272002664673280/
