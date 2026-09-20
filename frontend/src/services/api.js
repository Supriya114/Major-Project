const API_BASE = "http://127.0.0.1:8000";

async function request(path, options = {}) {
  const method = String(options.method || "GET").toUpperCase();
  const attempts = method === "GET" ? 2 : 1;
  let response;
  let networkError;

  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      response = await fetch(`${API_BASE}${path}`, {
        headers: {
          "Content-Type": "application/json",
          ...(options.headers || {}),
        },
        ...options,
      });
      networkError = null;
      break;
    } catch (error) {
      networkError = error;
      if (attempt + 1 < attempts) {
        await new Promise((resolve) => setTimeout(resolve, 600));
      }
    }
  }

  if (networkError || !response) {
    throw new Error(
      `Backend is not reachable at ${API_BASE}. Start FastAPI with: uvicorn app.main:app --reload`
    );
  }

  const text = await response.text();
  let body = {};
  try {
    body = text ? JSON.parse(text) : {};
  } catch {
    body = { detail: text };
  }

  if (!response.ok) {
    throw new Error(body.detail || `Request failed: ${response.status}`);
  }

  return body;
}

export function checkHealth() {
  return request("/api/health");
}

export function createProject(data) {
  return request("/api/projects", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export function listProjects() {
  return request("/api/projects");
}

export function deleteProject(projectId) {
  return request(`/api/projects/${projectId}`, {
    method: "DELETE",
  });
}


export function generateRequirements(projectId) {
  return request(`/api/projects/${projectId}/requirements/generate`, {
    method: "POST",
  });
}

export function getRequirements(projectId) {
  return request(`/api/projects/${projectId}/requirements`);
}

export function generateDeveloperOpinion(projectId) {
  return request(`/api/projects/${projectId}/developer-opinion`, {
    method: "POST",
  });
}

export function getDeveloperOpinion(projectId) {
  return request(`/api/projects/${projectId}/developer-opinion`);
}

export function getActivity(projectId) {
  return request(`/api/projects/${projectId}/activity`);
}

export const generateArchitecture = (projectId) =>
  request(`/api/projects/${projectId}/architecture/generate`, {
    method: "POST",
  });

export const getArchitecture = (projectId) =>
  request(`/api/projects/${projectId}/architecture`);

  export function getArchitectureVersions(projectId) {
    return request(
      `/api/projects/${projectId}/architecture/versions`
    );
  }
  
  export function getArchitectureVersion(
    projectId,
    version
  ) {
    return request(
      `/api/projects/${projectId}/architecture/versions/${version}`
    );
  }
  
  export function restoreArchitectureVersion(
    projectId,
    version
  ) {
    return request(
      `/api/projects/${projectId}/architecture/restore/${version}`,
      {
        method: "POST",
      }
    );
  }

export function updateRequirements(projectId, requirements) {
    return request(`/api/projects/${projectId}/requirements`, {
      method: "PUT",
      body: JSON.stringify(requirements),
    });
  }


  export function approveArchitecture(projectId) {
    return request(`/api/projects/${projectId}/architecture/approve`, {
      method: "POST",
    });
  }

  
  export function requestArchitectureRevision(projectId, feedback) {
    return request(`/api/projects/${projectId}/architecture/revision`, {
      method: "POST",
      body: JSON.stringify({
        feedback,
      }),
    });
  }

  export function generateDeveloperProject(projectId) {
    return request(`/api/projects/${projectId}/developer/generate`, {
      method: "POST",
    });
  }
  
  export function getDeveloperProject(projectId) {
    return request(`/api/projects/${projectId}/developer`);
  }

  export function generateTests(projectId) {
    return request(`/api/projects/${projectId}/tester/generate`, {
      method: "POST",
    });
  }
  
  export function getTests(projectId) {
    return request(`/api/projects/${projectId}/tester`);
  }
  
  export function addCustomTest(projectId, testCase) {
    return request(`/api/projects/${projectId}/tester/custom`, {
      method: "POST",
      body: JSON.stringify(testCase),
    });
  }

  export function runTests(projectId) {
    return request(`/api/projects/${projectId}/tester/run`, {
      method: "POST",
    });
  }

  export function approveTests(projectId) {
    return request(`/api/projects/${projectId}/tester/approve`, {
      method: "POST",
    });
  }
  export function generateReview(projectId) {
    return request(`/api/projects/${projectId}/reviewer/generate`, {
      method: "POST",
    });
  }
  
  export function getReview(projectId) {
    return request(`/api/projects/${projectId}/reviewer`);
  }

  export function approveReview(projectId) {
    return request(`/api/projects/${projectId}/reviewer/approve`, {
      method: "POST",
    });
  }

  export function startPreview(projectId) {
    return request(`/api/projects/${projectId}/preview/start`, {
      method: "POST",
    });
  }

  export function stopPreview(projectId) {
    return request(`/api/projects/${projectId}/preview/stop`, {
      method: "POST",
    });
  }

  export function requestDeveloperFixes(projectId) {
    return request(`/api/projects/${projectId}/developer/fix-request`, {
      method: "POST",
    });
  }
  export function getDeveloperFixRequest(projectId) {
    return request(`/api/projects/${projectId}/developer/fix-request`);
  }
export function approveRequirements(projectId) {
  return request(`/api/projects/${projectId}/requirements/approve`, { method: "POST" });
}

export function approveDeveloperProject(projectId) {
  return request(`/api/projects/${projectId}/developer/approve`, { method: "POST" });
}

export function getExportProjectUrl(projectId) {
  return `${API_BASE}/api/projects/${projectId}/export`;
}
