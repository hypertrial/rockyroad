import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "@tanstack/react-router";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { router } from "./router";
import "@fontsource-variable/fraunces/wght.css";
import "@fontsource-variable/manrope/wght.css";
import "./styles/foundation.css";
import "./styles/shell.css";
import "./styles/dashboard.css";
import "./styles/planner.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1 },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
);
