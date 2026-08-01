import { mount } from "svelte";
import App from "./App.svelte";
import "./lib/design.css";

const app = mount(App, { target: document.getElementById("app")! });

export default app;
