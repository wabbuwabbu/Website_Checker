const STATUS_URL = 'https://raw.githubusercontent.com/wabbuwabbu/Website_Checker/main/status.json';

async function updateStatus() {
    const response = await fetch(STATUS_URL);
    const data = await response.json();
    
    let html = '';
    for (const [site, details] of Object.entries(data)) {
        html += `
        <div class="status-card ${details.online ? 'online' : 'offline'}">
            <h2>${site}</h2>
            <p>Latency: ${details.latency}ms</p>
            <p>Uptime: ${details.uptime}%</p>
            <p>SSL Expiry: ${details.ssl_days_remaining} days</p>
            <p>Last Checked: ${details.last_check}</p>
        </div>
        `;
    }
    
    document.getElementById('status-container').innerHTML = html;
}

// Update every 5 minutes
setInterval(updateStatus, 300000);
updateStatus();