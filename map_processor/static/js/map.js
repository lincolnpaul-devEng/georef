/**
 * GeoRef Studio - Mapbox GL JS Mapping Engine
 * High-resolution satellite imagery, smooth camera panning (map.flyTo),
 * dynamic raster map overlays, 3D terrain, and glowing neon vector GCP radar overlays.
 */

document.addEventListener("DOMContentLoaded", function () {
  const mapElement = document.getElementById("map");
  if (!mapElement || !window.mapConfigData) return;

  const data = window.mapConfigData;
  const transformed = data.transformed_data || {};
  const bounds = transformed.leaflet_bounds; // [[south, west], [north, east]]
  const center = transformed.center ? [transformed.center[1], transformed.center[0]] : [36.82, -1.29]; // [lng, lat]
  const gcps = transformed.ground_control_points || [];
  const imageUrl = data.image_url || transformed.image_url;

  // 1. Resolve Mapbox Access Token (loaded securely from backend context)
  mapboxgl.accessToken = window.mapboxAccessToken || "";

  // 2. Initialize Mapbox GL JS Map
  let currentStyle = "mapbox://styles/mapbox/satellite-streets-v12";
  
  let map;
  try {
    map = new mapboxgl.Map({
      container: "map",
      style: currentStyle,
      center: center,
      zoom: 11,
      pitch: 0,
      bearing: 0,
      antialias: true
    });
  } catch (err) {
    console.error("Error initializing Mapbox GL JS:", err);
    return;
  }

  // Navigation & Scale Controls
  map.addControl(new mapboxgl.NavigationControl({ visualizePitch: true }), "top-left");
  map.addControl(new mapboxgl.ScaleControl({ unit: "metric" }), "bottom-left");
  map.addControl(new mapboxgl.FullscreenControl(), "top-left");

  // Format bounding coordinates for Mapbox Image Source:
  // Coordinates order: [top-left [lng, lat], top-right, bottom-right, bottom-left]
  let imageCoordinates = null;
  let mapboxBounds = null;

  if (bounds && bounds.length === 2) {
    const south = bounds[0][0];
    const west = bounds[0][1];
    const north = bounds[1][0];
    const east = bounds[1][1];

    imageCoordinates = [
      [west, north], // Top-Left
      [east, north], // Top-Right
      [east, south], // Bottom-Right
      [west, south]  // Bottom-Left
    ];

    mapboxBounds = [
      [west, south], // Southwest [lng, lat]
      [east, north]  // Northeast [lng, lat]
    ];
  }

  // 3. Setup Layers when Map Styles Load
  function setupMapLayers() {
    // 3A. 3D Terrain DEM Source
    if (!map.getSource("mapbox-dem")) {
      map.addSource("mapbox-dem", {
        type: "raster-dem",
        url: "mapbox://mapbox.mapbox-terrain-dem-v1",
        tileSize: 512,
        maxzoom: 14
      });
    }

    // 3B. Add Georeferenced Raster Map Overlay
    if (imageUrl && imageCoordinates) {
      if (!map.getSource("georef-raster-source")) {
        map.addSource("georef-raster-source", {
          type: "image",
          url: imageUrl,
          coordinates: imageCoordinates
        });
      }

      if (!map.getLayer("georef-raster-layer")) {
        map.addLayer({
          id: "georef-raster-layer",
          type: "raster",
          source: "georef-raster-source",
          paint: {
            "raster-opacity": parseFloat(document.getElementById("opacitySlider")?.value || 0.75),
            "raster-resampling": "linear",
            "raster-fade-duration": 200
          }
        });
      }
    }

    // 3C. Add Glowing Neon Vector Boundary Overlay
    if (imageCoordinates) {
      const polygonGeoJSON = {
        type: "Feature",
        geometry: {
          type: "Polygon",
          coordinates: [[
            imageCoordinates[0],
            imageCoordinates[1],
            imageCoordinates[2],
            imageCoordinates[3],
            imageCoordinates[0]
          ]]
        }
      };

      if (!map.getSource("georef-boundary-source")) {
        map.addSource("georef-boundary-source", {
          type: "geojson",
          data: polygonGeoJSON
        });
      }

      // Outer Neon Glow Line
      if (!map.getLayer("georef-boundary-glow")) {
        map.addLayer({
          id: "georef-boundary-glow",
          type: "line",
          source: "georef-boundary-source",
          paint: {
            "line-color": "#00f0ff",
            "line-width": 6,
            "line-blur": 5,
            "line-opacity": 0.85
          }
        });
      }

      // Sharp Core Neon Line
      if (!map.getLayer("georef-boundary-line")) {
        map.addLayer({
          id: "georef-boundary-line",
          type: "line",
          source: "georef-boundary-source",
          paint: {
            "line-color": "#ffffff",
            "line-width": 2,
            "line-dasharray": [3, 2]
          }
        });
      }
    }
  }

  // 4. Plot Glowing Neon Vector Radar Markers (GCPs)
  const gcpMarkers = [];

  function plotGcpRadarMarkers() {
    // Clear existing markers
    gcpMarkers.forEach(m => m.remove());
    gcpMarkers.length = 0;

    gcps.forEach((gcp, index) => {
      if (gcp.lat !== undefined && gcp.lng !== undefined) {
        // Create pulsing neon radar DOM element
        const markerEl = document.createElement("div");
        markerEl.className = "mapbox-neon-marker";
        markerEl.innerHTML = `
          <div class="radar-ring"></div>
          <div class="radar-ring ring-2"></div>
          <div class="radar-dot"></div>
        `;

        const popupHTML = `
          <div style="font-family: inherit; font-size: 13px; line-height: 1.5;">
            <div style="font-weight: 700; color: #00f0ff; margin-bottom: 4px; display: flex; align-items: center; gap: 4px;">
              <i class="bi bi-geo-fill"></i> ${gcp.label || 'Ground Control Point #' + (index + 1)}
            </div>
            <div style="color: #e2e8f0;">
              <strong>GPS:</strong> ${gcp.lat.toFixed(6)}°, ${gcp.lng.toFixed(6)}°<br/>
              ${gcp.easting ? `<strong>Easting:</strong> ${gcp.easting.toLocaleString()} m<br/>` : ''}
              ${gcp.northing ? `<strong>Northing:</strong> ${gcp.northing.toLocaleString()} m<br/>` : ''}
            </div>
            <button class="btn btn-sm btn-primary mt-2 py-0 px-2 w-100" style="font-size: 11px;" onclick="window.flyToPoint(${gcp.lng}, ${gcp.lat})">
              <i class="bi bi-camera-video me-1"></i> Cinematic Fly To
            </button>
          </div>
        `;

        const popup = new mapboxgl.Popup({ offset: 15, closeButton: true })
          .setHTML(popupHTML);

        const marker = new mapboxgl.Marker({ element: markerEl, anchor: "center" })
          .setLngLat([gcp.lng, gcp.lat])
          .setPopup(popup)
          .addTo(map);

        gcpMarkers.push(marker);
      }
    });
  }

  // 5. Global Camera Animation Helper (map.flyTo)
  window.flyToPoint = function (lng, lat) {
    map.flyTo({
      center: [lng, lat],
      zoom: 16,
      pitch: 45,
      bearing: -15,
      duration: 2500,
      essential: true
    });
  };

  // 6. Map Load Event: Cinematic Panning & Bounds Fit
  map.on("load", function () {
    setupMapLayers();
    plotGcpRadarMarkers();

    // Cinematic entry animation with map.flyTo
    if (mapboxBounds) {
      map.fitBounds(mapboxBounds, {
        padding: { top: 60, bottom: 60, left: 60, right: 420 },
        maxZoom: 15,
        duration: 2500,
        pitch: 25,
        bearing: -5
      });
    }
  });

  // Re-add layers on style change
  map.on("style.load", function () {
    setupMapLayers();
    plotGcpRadarMarkers();
  });

  // 7. UI Controls & Event Listeners

  // Opacity Slider
  const opacitySlider = document.getElementById("opacitySlider");
  const opacityValDisplay = document.getElementById("opacityVal");

  if (opacitySlider) {
    opacitySlider.addEventListener("input", function (e) {
      const opacity = parseFloat(e.target.value);
      if (map.getLayer("georef-raster-layer")) {
        map.setPaintProperty("georef-raster-layer", "raster-opacity", opacity);
      }
      if (opacityValDisplay) {
        opacityValDisplay.textContent = `${Math.round(opacity * 100)}%`;
      }
    });
  }

  // Fit Bounds Button (Smooth map.flyTo)
  const btnFitBounds = document.getElementById("btnFitBounds");
  if (btnFitBounds && mapboxBounds) {
    btnFitBounds.addEventListener("click", function () {
      map.fitBounds(mapboxBounds, {
        padding: { top: 60, bottom: 60, left: 60, right: 420 },
        duration: 2000,
        pitch: 20
      });
    });
  }

  // 3D Terrain & Pitch Toggle
  const btnToggle3D = document.getElementById("btnToggle3D");
  let is3DActive = false;

  if (btnToggle3D) {
    btnToggle3D.addEventListener("click", function () {
      is3DActive = !is3DActive;
      btnToggle3D.classList.toggle("active", is3DActive);

      if (is3DActive) {
        map.setTerrain({ source: "mapbox-dem", exaggeration: 1.5 });
        map.flyTo({
          pitch: 60,
          bearing: -30,
          duration: 2500,
          essential: true
        });
      } else {
        map.setTerrain(null);
        map.flyTo({
          pitch: 0,
          bearing: 0,
          duration: 2000,
          essential: true
        });
      }
    });
  }

  // Base Style Switcher Buttons
  const styleSelect = document.getElementById("mapStyleSelect");
  if (styleSelect) {
    styleSelect.addEventListener("change", function (e) {
      currentStyle = e.target.value;
      map.setStyle(currentStyle);
    });
  }

  // GCP Table Row Click -> Smooth flyTo
  const gcpRows = document.querySelectorAll(".gcp-row-clickable");
  gcpRows.forEach(row => {
    row.addEventListener("click", function () {
      const lat = parseFloat(this.dataset.lat);
      const lng = parseFloat(this.dataset.lng);
      if (!isNaN(lat) && !isNaN(lng)) {
        window.flyToPoint(lng, lat);
      }
    });
  });
});
