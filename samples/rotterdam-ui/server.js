const express = require("express");
const app = express();
const PORT = process.env.PORT || 3000;
const API_URL = process.env.API_URL || "http://localhost:8080";

app.get("/health", (req, res) => {
  res.json({ status: "ok", service: "rotterdam-ui" });
});

app.get("/", (req, res) => {
  res.send(`<!DOCTYPE html>
<html>
<head><title>Rotterdam UI</title>
<style>body{font-family:system-ui;background:#111;color:#eee;max-width:600px;margin:60px auto;padding:20px}
h1{color:#10b981}code{background:#222;padding:2px 6px;border-radius:4px}
.card{background:#1a1a1a;border:1px solid #333;border-radius:12px;padding:20px;margin:16px 0}
.ok{color:#10b981}.err{color:#ef4444}button{background:#10b981;color:#000;border:0;padding:8px 16px;border-radius:8px;cursor:pointer;font-weight:600}</style>
</head>
<body>
<h1>Rotterdam UI</h1>
<p>Haven Platform test frontend — connected to <code>${API_URL}</code></p>
<div class="card"><h3>API Health</h3><pre id="health">Loading...</pre></div>
<div class="card"><h3>DB Test</h3><button onclick="testDb()">Test PostgreSQL</button><pre id="db"></pre></div>
<div class="card"><h3>Redis Test</h3><button onclick="testRedis()">Test Redis</button><pre id="redis"></pre></div>
<script>
fetch("${API_URL}/health").then(r=>r.json()).then(d=>{document.getElementById("health").textContent=JSON.stringify(d,null,2)}).catch(e=>{document.getElementById("health").innerHTML='<span class="err">'+e+'</span>'});
function testDb(){fetch("${API_URL}/db-test").then(r=>r.json()).then(d=>{document.getElementById("db").textContent=JSON.stringify(d,null,2)})}
function testRedis(){fetch("${API_URL}/redis-test").then(r=>r.json()).then(d=>{document.getElementById("redis").textContent=JSON.stringify(d,null,2)})}
</script>
</body></html>`);
});

app.listen(PORT, () => console.log(`Rotterdam UI on port ${PORT}`));
