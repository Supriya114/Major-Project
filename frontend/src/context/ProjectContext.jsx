import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

const ProjectContext = createContext(null);
const STORAGE_KEY = "smartdevagents.activeProject.v3";

const initialProject = {
  id: null,
  name: "No project selected",
  description: "Create a project to begin the AI-driven SDLC workflow.",
  status: "IDLE",
  currentAgent: "PRODUCT_MANAGER",
};

export function ProjectProvider({ children }) {
  const [project, setProjectState] = useState(initialProject);

  useEffect(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved);
        if (parsed?.id) setProjectState(parsed);
      }
    } catch {
      localStorage.removeItem(STORAGE_KEY);
    }
  }, []);

  const setProject = useCallback((next) => {
    setProjectState((current) => {
      const value = typeof next === "function" ? next(current) : next;
      try {
        if (value?.id) localStorage.setItem(STORAGE_KEY, JSON.stringify(value));
        else localStorage.removeItem(STORAGE_KEY);
      } catch {
        // Storage is an enhancement; workflow state remains in memory.
      }
      return value;
    });
  }, []);

  const value = useMemo(() => ({ project, setProject }), [project, setProject]);

  return <ProjectContext.Provider value={value}>{children}</ProjectContext.Provider>;
}

export function useProject() {
  return useContext(ProjectContext);
}
