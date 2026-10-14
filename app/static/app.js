const defaultLocation = { latitude: 19.076, longitude: 72.8777, name: "Mumbai" };
const map = L.map("map", { zoomControl: false }).setView([defaultLocation.latitude, defaultLocation.longitude], 10);
L.control.zoom({ position: "bottomleft" }).addTo(map);
const satelliteLayer = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {
  maxZoom: 19,
  attribution: "Tiles &copy; Esri, Maxar, Earthstar Geographics, and the GIS User Community",
});
const streetLayer = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
});
satelliteLayer.addTo(map);
L.control.layers({ "Satellite": satelliteLayer, "Street map": streetLayer }, null, {
  collapsed: true,
  position: "topright",
}).addTo(map);
map.on("baselayerchange", (event) => {
  document.getElementById("map-layer-name").textContent = event.name === "Satellite" ? "Satellite overview" : "Street map";
});

let selectedLocation = { ...defaultLocation };
let marker;
let messageTimer;

function iconify() {
  if (window.lucide) window.lucide.createIcons();
}

function showMessage(message) {
  const node = document.getElementById("map-message");
  node.textContent = message;
  node.classList.add("visible");
  window.clearTimeout(messageTimer);
  messageTimer = window.setTimeout(() => node.classList.remove("visible"), 3200);
}

function riskLabel(level) {
  return (level || "unknown").replaceAll("_", " ");
}

function setMarker(latitude, longitude, heatIndex, riskLevel) {
  const markerIcon = L.divIcon({
    className: "",
    html: `<div class="risk-marker" data-risk="${riskLevel}">${Math.round(heatIndex)}°</div>`,
    iconSize: [46, 46],
    iconAnchor: [23, 23],
  });
  if (!marker) marker = L.marker([latitude, longitude], { icon: markerIcon }).addTo(map);
  else marker.setLatLng([latitude, longitude]).setIcon(markerIcon);
}

function renderForecast(days) {
  const list = document.getElementById("forecast-list");
  list.replaceChildren();
  days.forEach((day, index) => {
    const date = new Date(`${day.date}T12:00:00`);
    const row = document.createElement("div");
    row.className = "forecast-row";
    const label = index === 0 ? "Today" : date.toLocaleDateString(undefined, { weekday: "short" });
    const shortDate = date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
    row.innerHTML = `<span class="forecast-day">${label}<span class="forecast-date">${shortDate}</span></span><span class="forecast-risk" data-risk="${day.risk_level}"><i></i>${riskLabel(day.risk_level)}</span><span class="forecast-temp">${Math.round(day.maximum_temperature_c)}°</span><span class="forecast-index">${Math.round(day.maximum_heat_index_c)}° HI</span>`;
    list.append(row);
  });
}

function renderRecommendations(items) {
  const list = document.getElementById("recommendations");
  list.replaceChildren();
  items.slice(0, 2).forEach((recommendation) => {
    const item = document.createElement("li");
    item.textContent = recommendation;
    list.append(item);
  });
}

async function loadLocation(location, shouldMoveMap = true) {
  selectedLocation = location;
  const locationName = document.getElementById("location-name");
  locationName.textContent = location.name || `${location.latitude.toFixed(3)}, ${location.longitude.toFixed(3)}`;
  document.getElementById("coordinates").textContent = `${Math.abs(location.latitude).toFixed(4)} ${location.latitude >= 0 ? "N" : "S"}, ${Math.abs(location.longitude).toFixed(4)} ${location.longitude >= 0 ? "E" : "W"}`;
  document.getElementById("updated-at").textContent = "Updating…";
  document.getElementById("risk-level").textContent = "Loading";
  if (shouldMoveMap) map.flyTo([location.latitude, location.longitude], Math.max(map.getZoom(), 9), { duration: 0.65 });

  try {
    const response = await fetch(`/api/v1/heat-risk/live?latitude=${encodeURIComponent(location.latitude)}&longitude=${encodeURIComponent(location.longitude)}`);
    const report = await response.json();
    if (!response.ok) throw new Error(report.detail || "Live weather is unavailable right now.");
    if (selectedLocation !== location) return;

    const current = report.current;
    const riskDisplay = document.getElementById("risk-display");
    riskDisplay.dataset.risk = current.risk_level;
    document.getElementById("heat-index").textContent = current.heat_index_c.toFixed(1);
    document.getElementById("risk-level").textContent = riskLabel(current.risk_level);
    document.getElementById("air-temperature").textContent = `${Math.round(current.temperature_c)}°`;
    document.getElementById("humidity").textContent = `${Math.round(current.humidity_percent)}%`;
    document.getElementById("timezone").textContent = report.location.timezone || "Local";
    const fetchedAt = new Date(report.fetched_at);
    document.getElementById("updated-at").textContent = `Updated ${fetchedAt.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;
    const outlook = report.heatwave_outlook;
    const heatwaveNote = document.getElementById("heatwave-note");
    heatwaveNote.classList.toggle("is-hot", outlook.potential_heatwave || outlook.status === "extreme_heat_watch");
    document.getElementById("heatwave-status").textContent = outlook.potential_heatwave
      ? `Potential heatwave · ${outlook.periods[0].duration_days} consecutive days`
      : outlook.status === "extreme_heat_watch" ? "Extreme heat in the forecast" : "No heatwave signal in forecast";
    renderForecast(report.daily_outlook);
    renderRecommendations(current.recommendations);
    setMarker(location.latitude, location.longitude, current.heat_index_c, current.risk_level);
    iconify();
  } catch (error) {
    document.getElementById("updated-at").textContent = "Data unavailable";
    document.getElementById("risk-level").textContent = "Unavailable";
    document.getElementById("forecast-list").innerHTML = '<div class="forecast-empty">Live forecast could not be loaded.</div>';
    showMessage(error.message);
  }
}

map.on("click", (event) => {
  loadLocation({ latitude: event.latlng.lat, longitude: event.latlng.lng });
});

document.getElementById("search-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const query = document.getElementById("location-search").value.trim();
  if (!query) return;
  const submitButton = event.currentTarget.querySelector("button");
  submitButton.disabled = true;
  try {
    const response = await fetch(`https://geocoding-api.open-meteo.com/v1/search?name=${encodeURIComponent(query)}&count=1&language=en&format=json`);
    const result = await response.json();
    if (!result.results?.length) throw new Error("No matching city found.");
    const place = result.results[0];
    const name = [place.name, place.admin1, place.country].filter((part, index, all) => part && all.indexOf(part) === index).join(", ");
    await loadLocation({ latitude: place.latitude, longitude: place.longitude, name });
  } catch (error) {
    showMessage(error.message || "City search is unavailable.");
  } finally {
    submitButton.disabled = false;
  }
});

document.getElementById("locate-button").addEventListener("click", () => {
  if (!navigator.geolocation) {
    showMessage("Location services are not available in this browser.");
    return;
  }
  navigator.geolocation.getCurrentPosition(
    ({ coords }) => loadLocation({ latitude: coords.latitude, longitude: coords.longitude, name: "Your location" }),
    () => showMessage("Could not access your location. Check browser permissions."),
    { enableHighAccuracy: false, timeout: 10000 },
  );
});

iconify();
loadLocation(defaultLocation, false);
window.setInterval(() => loadLocation(selectedLocation, false), 15 * 60 * 1000);