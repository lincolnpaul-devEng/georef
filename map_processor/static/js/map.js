/**
 * GeoRef Studio - Mapbox GL JS Mapping & Cartographic Vector Engine
 * Precision Vector Overlay Harness, Self-Correcting Neatline Boundaries,
 * Color-Coded Cadastral Parcels, 3D Satellite Imagery, and Pulsing Radar GCP Markers.
 */

document.addEventListener("DOMContentLoaded", function () {
  const mapElement = document.getElementById("map");
  if (!mapElement || !window.mapConfigData) return;

  const data = window.mapConfigData;
  const transformed = data.transformed_data || {};
  const bounds = transformed.leaflet_bounds; // [[south, west], [north, east]]
  const center = transformed.center ? [transformed.center[1], transformed.center[0]] : [34.75, -0.08]; // [lng, lat]
  const gcps = transformed.ground_control_points || [];
  const imageUrl = data.image_url || transformed.image_url;
  const vectorLayers = transformed.vector_layers || null;
  const metrics = transformed.metrics || {};

  // 1. Resolve Mapbox Access Token
  mapboxgl.accessToken = window.mapboxAccessToken || "";

  // 2. Initialize Mapbox GL JS Map
  let currentStyle = "mapbox://styles/mapbox/satellite-streets-v12";
  
  let map;
  try {
    map = new mapboxgl.Map({
      container: "map",
      style: currentStyle,
      center: center,
      zoom: 13,
      pitch: 30,
      bearing: -5,
      antialias: true
    });
  } catch (err) {
    console.error("Error initializing Mapbox GL JS:", err);
    return;
  }

  // Navigation, Scale & Fullscreen Controls
  map.addControl(new mapboxgl.NavigationControl({ visualizePitch: true }), "top-left");
  map.addControl(new mapboxgl.ScaleControl({ unit: "metric" }), "bottom-left");
  map.addControl(new mapboxgl.FullscreenControl(), "top-left");

  // Format bounding coordinates
  let mapboxBounds = null;
  let imageCoordinates = null;

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

  // 3. Setup Vector Layers & Precision Overlays
  function setupMapLayers() {
    // 3A. 3D Terrain Source
    if (!map.getSource("mapbox-dem")) {
      map.addSource("mapbox-dem", {
        type: "raster-dem",
        url: "mapbox://mapbox.mapbox-terrain-dem-v1",
        tileSize: 512,
        maxzoom: 14
      });
    }

    // 3B. Precision Vector Layers (Neatlines, Grids, Cadastral Parcels)
    if (vectorLayers && vectorLayers.features) {
      if (!map.getSource("georef-vector-source")) {
        map.addSource("georef-vector-source", {
          type: "geojson",
          data: vectorLayers
        });
      }

      // Cadastral Parcel Fill Layer
      if (!map.getLayer("georef-cadastral-fill")) {
        map.addLayer({
          id: "georef-cadastral-fill",
          type: "fill",
          source: "georef-vector-source",
          filter: ["==", ["get", "layer_type"], "cadastral_parcel"],
          paint: {
            "fill-color": ["coalesce", ["get", "fill_color"], "rgba(0, 240, 255, 0.12)"],
            "fill-opacity": 0.85
          }
        });
      }

      // Cadastral Parcel Boundary Lines
      if (!map.getLayer("georef-cadastral-line")) {
        map.addLayer({
          id: "georef-cadastral-line",
          type: "line",
          source: "georef-vector-source",
          filter: ["==", ["get", "layer_type"], "cadastral_parcel"],
          paint: {
            "line-color": ["coalesce", ["get", "stroke_color"], "#10b981"],
            "line-width": 1.5,
            "line-opacity": 0.9
          }
        });
      }

      // Survey Grid Lines
      if (!map.getLayer("georef-grid-lines")) {
        map.addLayer({
          id: "georef-grid-lines",
          type: "line",
          source: "georef-vector-source",
          filter: ["==", ["get", "layer_type"], "grid_line"],
          paint: {
            "line-color": "#38bdf8",
            "line-width": 1.2,
            "line-dasharray": [4, 4],
            "line-opacity": 0.75
          }
        });
      }

      // Outer Neatline Glow Layer
      if (!map.getLayer("georef-neatline-glow")) {
        map.addLayer({
          id: "georef-neatline-glow",
          type: "line",
          source: "georef-vector-source",
          filter: ["==", ["get", "layer_type"], "neatline_boundary"],
          paint: {
            "line-color": "#00f0ff",
            "line-width": 6,
            "line-blur": 6,
            "line-opacity": 0.9
          }
        });
      }

      // Outer Neatline Crisp Edge
      if (!map.getLayer("georef-neatline-core")) {
        map.addLayer({
          id: "georef-neatline-core",
          type: "line",
          source: "georef-vector-source",
          filter: ["==", ["get", "layer_type"], "neatline_boundary"],
          paint: {
            "line-color": "#ffffff",
            "line-width": 2.5,
            "line-opacity": 1.0
          }
        });
      }
    }

    // 3C. Optional Scanned Raster Overlay (defaults to hidden / low blend in vector mode)
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
            "raster-opacity": parseFloat(document.getElementById("opacitySlider")?.value || 0.0),
            "raster-resampling": "linear",
            "raster-fade-duration": 200
          }
        });
      }
    }
  }

  // 4. Plot Glowing Neon Vector Radar Markers (GCPs)
  const gcpMarkers = [];

  function plotGcpRadarMarkers() {
    gcpMarkers.forEach(m => m.remove());
    gcpMarkers.length = 0;

    gcps.forEach((gcp, index) => {
      if (gcp.lat !== undefined && gcp.lng !== undefined) {
        const markerEl = document.createElement("div");
        markerEl.className = "mapbox-neon-marker";
        markerEl.innerHTML = `
          <div class="radar-ring"></div>
          <div class="radar-ring ring-2"></div>
          <div class="radar-dot"></div>
        `;

        const popupHTML = `
          <div style="font-family: inherit; font-size: 13px; line-height: 1.5; min-width: 220px;">
            <div style="font-weight: 700; color: #00f0ff; margin-bottom: 6px; display: flex; align-items: center; gap: 4px;">
              <i class="bi bi-crosshair text-primary"></i> ${gcp.label || 'Control Point #' + (index + 1)}
            </div>
            <div style="color: #e2e8f0; background: rgba(0,0,0,0.3); padding: 8px; border-radius: 6px;">
              <div><strong>GPS Lat:</strong> <span class="text-info">${gcp.lat.toFixed(6)}°</span></div>
              <div><strong>GPS Lng:</strong> <span class="text-info">${gcp.lng.toFixed(6)}°</span></div>
              ${gcp.easting ? `<div><strong>Easting:</strong> ${gcp.easting}</div>` : ''}
              ${gcp.northing ? `<div><strong>Northing:</strong> ${gcp.northing}</div>` : ''}
              ${gcp.self_corrected ? `<div class="badge bg-success mt-1"><i class="bi bi-shield-check"></i> Self-Corrected</div>` : ''}
            </div>
            <button class="btn btn-sm btn-primary mt-2 py-1 px-2 w-100 fw-semibold" style="font-size: 11px;" onclick="window.flyToPoint(${gcp.lng}, ${gcp.lat})">
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
      zoom: 16.5,
      pitch: 50,
      bearing: -15,
      duration: 2200,
      essential: true
    });
  };

  // 6. Interactive Parcel Hover Tooltip
  const hoverPopup = new mapboxgl.Popup({
    closeButton: false,
    closeOnClick: false
  });

  map.on("mousemove", "georef-cadastral-fill", function (e) {
    map.getCanvas().style.cursor = "pointer";
    if (e.features.length > 0) {
      const feat = e.features[0];
      const props = feat.properties;
      const html = `
        <div style="font-size: 12px; font-weight: 600; color: #fff;">
          <i class="bi bi-bounding-box text-success me-1"></i> ${props.parcel_id || 'Cadastral Parcel'}<br/>
          <span class="text-muted small">${props.section || 'Survey Section'}</span><br/>
          <span class="text-warning small"><i class="bi bi-rulers"></i> ${props.area_acres || '0.5'} Acres</span>
        </div>
      `;
      hoverPopup.setLngLat(e.lngLat).setHTML(html).addTo(map);
    }
  });

  map.on("mouseleave", "georef-cadastral-fill", function () {
    map.getCanvas().style.cursor = "";
    hoverPopup.remove();
  });

  // 7. Map Load Event: Cinematic Panning & Bounds Fit
  map.on("load", function () {
    setupMapLayers();
    plotGcpRadarMarkers();

    if (mapboxBounds) {
      map.fitBounds(mapboxBounds, {
        padding: { top: 70, bottom: 70, left: 70, right: 440 },
        maxZoom: 16,
        duration: 2500,
        pitch: 35,
        bearing: -5
      });
    }
  });

  // Re-add layers on style change
  map.on("style.load", function () {
    setupMapLayers();
    plotGcpRadarMarkers();
  });

  // 8. UI Controls & Event Listeners

  // Vector Mode Selector
  const vectorModeSelect = document.getElementById("vectorModeSelect");
  if (vectorModeSelect) {
    vectorModeSelect.addEventListener("change", function (e) {
      const mode = e.target.value;
      if (mode === "vector_only") {
        if (map.getLayer("georef-raster-layer")) map.setPaintProperty("georef-raster-layer", "raster-opacity", 0.0);
        if (map.getLayer("georef-cadastral-fill")) map.setLayoutProperty("georef-cadastral-fill", "visibility", "visible");
        if (map.getLayer("georef-grid-lines")) map.setLayoutProperty("georef-grid-lines", "visibility", "visible");
      } else if (mode === "cadastral_color") {
        if (map.getLayer("georef-raster-layer")) map.setPaintProperty("georef-raster-layer", "raster-opacity", 0.0);
        if (map.getLayer("georef-cadastral-fill")) {
          map.setLayoutProperty("georef-cadastral-fill", "visibility", "visible");
          map.setPaintProperty("georef-cadastral-fill", "fill-opacity", 0.45);
        }
      } else if (mode === "raster_blend") {
        if (map.getLayer("georef-raster-layer")) map.setPaintProperty("georef-raster-layer", "raster-opacity", 0.75);
      }
    });
  }

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
        padding: { top: 70, bottom: 70, left: 70, right: 440 },
        duration: 2000,
        pitch: 30
      });
    });
  }

  // 3D Terrain & Relief Pitch Toggle
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
          bearing: -35,
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
