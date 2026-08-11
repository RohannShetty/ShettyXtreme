# ShettyXtreme — Plain-English Manual

*Written for a human, not a programmer. If anything here is unclear, the "Getting help" section at the end points you to the full docs.*

## What is ShettyXtreme

ShettyXtreme is an options trading dashboard for the Indian market. It puts the things you would normally need four different tools for onto one screen: a live option chain, a market scanner, research briefs, your positions and risk, and a learning memory that keeps notes for you.

It watches NIFTY and BANKNIFTY option chains, and gets its market data from Fyers, your broker. The whole thing runs on your own PC. Your Fyers login details stay on your PC, and nothing happens without you — the terminal never trades on its own.

## First-run checklist

Getting going takes four steps. You do them once, and from then on the terminal connects by itself when you start it.

1. **Start the terminal.** Open PowerShell (press the Windows key, type "PowerShell", press Enter). Then type this line and press Enter:

   `.venv\Scripts\python.exe run.py --mode OBSERVER`

   Then open your browser and go to `http://127.0.0.1:8000`. It takes you to the setup page.
2. **Know your way back.** At the very top of the browser window there is a small tag that shows SETUP, CONNECTED, or REAUTH. Clicking that tag takes you to the setup page and the settings page any time you need them.
3. **Connect your Fyers account.** The next section shows how to do this.
4. **Check the tag.** When the connection is good, the tag at the top shows CONNECTED.

## Connect your Fyers account

The setup page walks you through this. You only need to do it once.

**Step 1: Create a Fyers app (one-time setup).**

A "Fyers app" is not something you install on your phone. It is a registration you create on the Fyers Developer Portal, and it gives ShettyXtreme permission to use your Fyers account. You can create one in a few minutes.

1. Go to the [Fyers Developer Portal](https://myapi.fyers.in/) and log in with your Fyers account.
2. Create a new app. Give it any name you like (e.g., "ShettyXtreme").
3. Make sure you enable **Trading API** on the app.
4. Set the **Redirect URL** to `http://127.0.0.1:8000/auth/fyers/callback` — this is where Fyers sends you back after you log in.
5. Note down the **App ID** and **Secret ID** — you will need these in the next step.

**Step 2: Connect from the setup page.**

On the setup page, fill in two boxes:

- **App ID** — the App ID from the Fyers Developer Portal (looks like `ABC-123`).
- **Secret ID** — the Secret ID from the Fyers Developer Portal (a long secret code).

Press the **Test** button first — it checks your details without connecting anything. When it says the details are good, press **Connect Fyers**.

You will be redirected to Fyers to log in. After you approve, you come back to the terminal and it shows CONNECTED.

**Where your details are stored.**

Everything you enter is saved in one encrypted file on your PC. Nobody can read it without your PC's login. If you ever change your Fyers password, or the connection stops working, connect again from the setup page — it takes a minute.

## The three modes — OBSERVER, PAPER, LIVE

The terminal runs in one of three modes. You choose the mode when you start it.

- **OBSERVER (default).** Watch only. The terminal shows you everything — chains, scanner, research — but it never places an order. Nothing is ever bought or sold in this mode. This is the safe mode, and the one that starts by default.
- **PAPER.** Practice money. Orders are filled against a pretend balance, so you can rehearse a strategy without risking a rupee.
- **LIVE.** Real orders, real money. To start in this mode you must type out a confirmation when the terminal asks. The terminal never switches to LIVE by itself, and never brings LIVE back after a restart. Even in LIVE, every order needs your approval in the terminal before it goes anywhere.

**The kill switch.** Pressing Ctrl+Shift+K stops everything, in any mode. It is always available, even while a screen is loading. If you are ever unsure what is happening, press it.

## What you see on screen

- **Watchlist (left).** Your saved symbols with live prices. Add the stocks and indices you trade most, and they are always one glance away.
- **Option Chain (center).** The heart of the screen. Strikes, premiums, and live prices for the expiry you picked. This is where you read a chain the way you would on a broker app.
- **Scanner.** Sweeps many symbols for activity — big moves, heavy volume, unusual movement — so you notice an opportunity without watching every chain yourself.
- **Strategy Hints.** Gentle suggestions based on what is on screen, like spreads or hedges worth considering. They are ideas, not instructions.
- **Research (AI briefs).** A short research note about a symbol, written by AI and shown with two buttons: **Approve** and **Reject**. Approving keeps the note in your learning memory. Rejecting drops it. You decide what gets remembered.
- **Knowledge.** Your learning memory. Every research note you approved, plus any notes you wrote yourself, stays here and can be searched later.
- **Analytics.** Charts and numbers about how things are moving — useful for spotting patterns through the day.
- **Positions and Risk (bottom strip).** Your open positions and live risk figures, such as total exposure. One glance tells you how much is at stake right now.
- **Right Dock (right side).** Three tabs you can switch between:
  - **Proposals** — trade ideas waiting for your approval. Each one shows the symbol, action (buy/sell), quantity, and price. You approve or reject each one.
  - **Research** — AI research briefs and your knowledge base. Run a brief on any symbol, approve or reject what the AI found, and search your saved notes.
  - **Logs** — a running record of what the terminal is doing. If something looks odd, the answer is usually in here.

## Keyboard shortcuts

A few keys answer directly, without reaching for the mouse. You can see the same list inside the terminal any time — press **Ctrl+/** (or **Ctrl+?**) or click the keyboard button at the top right of the screen.

- **Ctrl+K** — Open the command palette. Type a few letters to jump to any screen or action.
- **Ctrl+R** — Show or hide the right-hand panel (proposals, research, and logs).
- **Ctrl+M** — Move through the three modes: OBSERVER → PAPER → LIVE → back to OBSERVER. Landing on LIVE still asks you to type the confirmation.
- **Ctrl+F** — Jump straight to the knowledge search box.
- **Ctrl+Shift+K** — The kill switch. Stops everything instantly, in any mode, on any screen. If you are ever unsure what is happening, press it.

## Errors explained in plain words

- **"Token expired".** Fyers security codes expire every day, around 3 AM. When that happens, the tag at the top shows REAUTH. Go to the settings page, choose Re-auth, and connect again — it takes a minute.
- **"Data API entitlement missing".** This means your Fyers app does not have permission to fetch market data. It is not a bug in ShettyXtreme, and it is not about your password. Fix it by going to the Fyers Developer Portal and enabling Market Data on your app. Prices start flowing after that.
- **"Port 8000 already in use".** Another copy of the terminal is already running. Close the other one and start again, or keep using the copy that is running. Two copies cannot share the same window at once.

## Good habits and safety

- **Keep the terminal in OBSERVER unless you are sure.** You can watch everything for weeks in OBSERVER without any risk.
- **Re-auth before market opens.** The code expires around 3 AM, so connecting fresh before 9:15 keeps the whole day smooth.
- **The kill switch is always visible.** Ctrl+Shift+K works in every mode and on every screen.
- **Expiry day alerts are normal.** On option expiry day (usually Thursday), the chain moves sharply and the scanner shows more alerts than usual. That is the market, not a fault.
- **Treat research briefs as one opinion.** They help you think. They do not decide for you.

## Getting help

- The **docs folder** (`docs/` in this project) holds the full written guides for anyone who wants the detail.
- The **changelog** (`CHANGELOG.md`) lists what changed in each version, in plain order.
- ShettyXtreme is a **personal-use tool**. There is no support desk behind it — the docs and the logs are your helpers.
- Nothing here is **investment advice**. Prices can move against you, and only you decide what to trade.
