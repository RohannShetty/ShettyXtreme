# ShettyXtreme — Plain-English Manual

*Written for a human, not a programmer. If anything here is unclear, the "Getting help" section at the end points you to the full docs.*

## What is ShettyXtreme

ShettyXtreme is an options trading dashboard for the Indian market. It puts the things you would normally need four different tools for onto one screen: a live option chain, a market scanner, research briefs, your positions and risk, and a learning memory that keeps notes for you.

It watches NIFTY and BANKNIFTY option chains, and gets its market data from Dhan, your broker. The whole thing runs on your own PC. Your Dhan login details stay on your PC, and nothing happens without you — the terminal never trades on its own.

## First-run checklist

Getting going takes four steps. You do them once, and from then on the terminal connects by itself when you start it.

1. **Start the terminal.** Open PowerShell (press the Windows key, type "PowerShell", press Enter). Then type this line and press Enter:

   `.venv\Scripts\python.exe run.py --mode OBSERVER`

   Then open your browser and go to `http://127.0.0.1:8000`. It takes you to the setup page.
2. **Know your way back.** At the very top of the browser window there is a small tag that shows SETUP, CONNECTED, or REAUTH. Clicking that tag takes you to the setup page and the settings page any time you need them.
3. **Connect your Dhan account.** The next section shows the three ways to do this.
4. **Check the tag.** When the connection is good, the tag at the top shows CONNECTED.

## Connect your Dhan account — 3 ways

The setup page walks you through this. You only need one of the three ways.

**Option 1: App credentials (recommended).**

A "Dhan app" is not something you install on your phone. It is a registration you create on the Dhan developer website, and it gives programs permission to use your Dhan account. You can create one in a few minutes — the Dhan site explains it step by step.

When you create the app, make sure it has **both** Trading and Market Data access. If it only has Trading, prices will not come through and you will see error 806 (explained in the errors section).

On the setup page you fill in three boxes:

- **Client ID** — your Dhan user name.
- **API key** and **API secret** — two long secret codes that Dhan shows you when the app is created. Think of them as the app's password.

Press the **Test** button first — it checks your details without connecting anything. When it says the details are good, press **Connect Dhan**.

**Option 2: Direct token.**

If you already have a Dhan access token (a long code that proves your identity), paste it into the box. The terminal reads your client ID and the token's expiry date by itself. This is the quickest way if you generate tokens on the Dhan site.

**Option 3: PIN + TOTP.**

Type your Dhan client ID, your 4-digit trading PIN, and the 6-digit code from your authenticator app (the one that changes every 30 seconds). This is the easiest way to connect on the spot.

**Data token (optional, for advanced users).**

Only needed if your app cannot get market data. It adds a separate code for data, so the rest of your connection can stay the way it is. Most people never need this.

**Where your details are stored.**

Everything you enter is saved in one encrypted file on your PC. Nobody can read it without your PC's login. If you ever change your Dhan password, or the connection stops working, connect again from the setup page — it takes a minute.

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
- **Logs (right).** A running, plain record of what the terminal is doing. If something looks odd, the answer is usually in here — and it is useful to quote from when asking for help.

## Keyboard shortcuts

A few keys answer directly, without reaching for the mouse. You can see the same list inside the terminal any time — press **Ctrl+/** (or **Ctrl+?**) or click the keyboard button at the top right of the screen.

- **Ctrl+R** — Show or hide the right-hand panel (logs, proposals, research, and knowledge).
- **Ctrl+M** — Move through the three modes: OBSERVER → PAPER → LIVE → back to OBSERVER. Landing on LIVE still asks you to type the confirmation.
- **Ctrl+F** — Jump straight to the knowledge search box.
- **Ctrl+Shift+K** — The kill switch. Stops everything instantly, in any mode, on any screen. If you are ever unsure what is happening, press it.

## Errors explained in plain words

- **Error 806.** This one worries people the most. It means your Dhan app is not allowed to fetch market data. It is not a bug in ShettyXtreme, and it is not about your password. Fix it by going to the Dhan developer website and enabling Market Data on your app (or add a data token, described earlier). Prices start flowing after that.
- **"Token expired".** Dhan security codes expire every day, around 3 AM. When that happens, the tag at the top shows REAUTH. Go to the settings page, choose Re-auth, and connect again — it takes a minute.
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
