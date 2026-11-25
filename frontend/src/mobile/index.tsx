import React from "react";
import ReactDOM from "react-dom/client";
import MobileApp from "./MobileApp";
import "../index.css";

const rootElement = document.getElementById("mobile-root");
if (rootElement) {
  ReactDOM.createRoot(rootElement).render(
    <React.StrictMode>
      <MobileApp />
    </React.StrictMode>
  );
}

