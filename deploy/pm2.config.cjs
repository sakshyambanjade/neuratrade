module.exports = {
  apps: [
    {
      name: "api",
      script: "uvicorn",
      args: "main:app --host 0.0.0.0 --port 8000",
      cwd: "./backend",
      interpreter: "./.venv/Scripts/python.exe",
      autorestart: true,
    },
    {
      name: "trading-loop",
      script: "python",
      args: "-m workers.trading_loop",
      cwd: "./backend",
      interpreter: "./.venv/Scripts/python.exe",
      autorestart: true,
    },
  ],
};
