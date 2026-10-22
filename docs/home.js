// The site page counts its own view, with the allowlist and the opt-outs the app uses.
import { install } from "./app/guard.js";
import { count } from "./app/stats.js";

install(window);
count("page", "home");
