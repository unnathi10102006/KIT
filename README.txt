LOCAL FARMER MARKET INFORMATION SYSTEM - VERSION 2
==================================================
Features: Dashboard, Live Prices, Nearby Buyers, My Crops (with photos), AI Advisor, Log out.

RUN IN VS CODE
  1. File > Open Folder > select this folder (farmer_market_v2)
  2. Terminal > New Terminal  (it opens as Command Prompt)
  3. python -m venv venv
  4. venv\Scripts\activate
  5. pip install -r requirements.txt
  6. python app.py
  7. Open http://localhost:5000  (phone: use the address printed in the terminal, same Wi-Fi)

DEMO LOGIN: phone 9999999999 / password demo123
Stop the server: CTRL+C

OPTIONAL: real AI answers with Claude
  Set your key before running:   set ANTHROPIC_API_KEY=your-key-here
  Without a key the advisor uses its built-in rules.
