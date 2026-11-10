// Made-up data for the browser-only demo backend (?demo). Not real anglers, trips or spots.
export const DEMO_EMAIL = "demo@example.com";

export function demoSeed() {
  return {
    users: [
      { email: DEMO_EMAIL, name: "Demo Angler", role: "admin" },
      { email: "buddy@example.com", name: "Fishing Buddy", role: "member" },
    ],
  };
}
