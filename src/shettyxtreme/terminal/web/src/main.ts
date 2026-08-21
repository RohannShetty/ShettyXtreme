import { mount } from "svelte";
import App from "./App.svelte";
import "./lib/app.css";
import "./lib/design.css";
import { initTheme } from "./lib/theme";
import { initColorConvention } from "./lib/color-convention";

initTheme();
initColorConvention();

const app = mount(App, { target: document.getElementById("app")! });

export default app;
