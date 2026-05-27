#!/usr/bin/env python3
"""Generate all skill SKILL.md files under ~/.gemini/antigravity-cli/skills/"""
import os
import textwrap

SKILLS_DIR = os.path.expanduser("~/.gemini/antigravity-cli/skills")

SKILLS = {
    # Category: Google Cloud / GCP
    "gcp-cloud-run": ("Google Cloud / GCP", "Deploy, configure, and manage services on Google Cloud Run, including scaling, traffic splitting, and Cloud Run Jobs."),
    "cloud-run-basics": ("Google Cloud / GCP", "Understand Cloud Run fundamentals: containerized deployments, service configuration, environment variables, and IAM."),
    "cloud-sql-basics": ("Google Cloud / GCP", "Work with Cloud SQL instances, connections via proxy or connector, database creation, and IAM authentication."),
    "bigquery-basics": ("Google Cloud / GCP", "Query, manage, and optimize BigQuery datasets, tables, and jobs using SQL and the Python client library."),
    "firebase-basics": ("Google Cloud / GCP", "Build and manage Firebase projects including Firestore, Authentication, Hosting, and Cloud Functions."),
    "gke-basics": ("Google Cloud / GCP", "Deploy and manage containerized workloads on Google Kubernetes Engine including cluster creation and kubectl operations."),
    "alloydb-basics": ("Google Cloud / GCP", "Work with AlloyDB clusters, instances, and PostgreSQL-compatible interfaces including connection management and IAM."),
    "google-cloud-recipe-auth": ("Google Cloud / GCP", "Implement GCP authentication patterns: service accounts, workload identity federation, ADC, and OAuth2."),
    "google-cloud-recipe-onboarding": ("Google Cloud / GCP", "Onboard new GCP projects: enable APIs, set up IAM, configure billing, and establish resource hierarchy."),
    "google-cloud-networking-observability": ("Google Cloud / GCP", "Monitor and troubleshoot GCP networking: VPC flow logs, Network Intelligence Center, and Packet Mirroring."),
    "google-cloud-waf-basics": ("Google Cloud / GCP", "Configure Cloud Armor WAF policies, security rules, and rate limiting for GCP load balancers."),
    "google-cloud-waf-rules": ("Google Cloud / GCP", "Write and manage Cloud Armor WAF rules including pre-configured rules, custom expressions, and adaptive protection."),
    "google-cloud-waf-config": ("Google Cloud / GCP", "Advanced Cloud Armor configuration: backend security policies, security policy scopes, and edge security policies."),

    # Category: Gemini / ADK / Agent Platform
    "gemini-api": ("Gemini / ADK / Agent Platform", "Use the Gemini API for generative AI tasks including text generation, multimodal inputs, embeddings, and streaming."),
    "gemini-api-dev": ("Gemini / ADK / Agent Platform", "Develop applications with the Gemini API: authentication, model selection, prompt engineering, and error handling."),
    "gemini-api-integration": ("Gemini / ADK / Agent Platform", "Integrate Gemini API into existing applications with best practices for latency, caching, and safety settings."),
    "gemini-interactions-api": ("Gemini / ADK / Agent Platform", "Build interactive multi-turn conversation flows using Gemini's chat and context window capabilities."),
    "gemini-managed-agents-api": ("Gemini / ADK / Agent Platform", "Deploy and manage agents using Vertex AI Agent Engine (Reasoning Engine) with the managed agents API."),
    "google-agents-cli-basics": ("Gemini / ADK / Agent Platform", "Get started with the Google Agents CLI: installation, project setup, agent creation, and basic commands."),
    "google-agents-cli-advanced": ("Gemini / ADK / Agent Platform", "Advanced Agents CLI usage: custom tools, sub-agents, multi-agent pipelines, and agent composition patterns."),
    "google-agents-cli-deploy": ("Gemini / ADK / Agent Platform", "Deploy agents to Agent Runtime using Agents CLI: packaging, deployment configuration, and update workflows."),
    "google-agents-cli-eval": ("Gemini / ADK / Agent Platform", "Evaluate agent quality using Agents CLI: eval sets, metrics, batch evaluation, and regression detection."),
    "google-agents-cli-auth": ("Gemini / ADK / Agent Platform", "Configure authentication in Agents CLI: service accounts, workload identity, Agent Identity, and SPIFFE."),
    "google-agents-cli-config": ("Gemini / ADK / Agent Platform", "Manage Agents CLI project configuration: .env files, config.py patterns, environment variables, and secrets."),
    "google-agents-cli-plugins": ("Gemini / ADK / Agent Platform", "Extend the Agents CLI with plugins: MCP servers, custom tool providers, and plugin configuration."),

    # Category: Agent Development
    "ai-agent-development": ("Agent Development", "Build production AI agents: tool use, memory, planning, grounding, and agent lifecycle management."),
    "ai-agents-architect": ("Agent Development", "Architect multi-agent systems: delegation patterns, agent hierarchies, communication protocols, and failure modes."),
    "ai-engineer": ("Agent Development", "Apply AI engineering best practices: model selection, prompt optimization, evaluation, and deployment pipelines."),
    "ai-engineering-toolkit": ("Agent Development", "Use the AI engineering toolkit: ADK, LiteLLM, LangChain, evaluation frameworks, and observability tools."),
    "multi-agent-orchestrator": ("Agent Development", "Orchestrate multi-agent workflows: coordinator patterns, agent routing, result aggregation, and error recovery."),
    "multi-agent-eval": ("Agent Development", "Evaluate multi-agent systems: end-to-end test cases, agent interaction traces, and quality metrics."),
    "autonomous-agent-patterns": ("Agent Development", "Implement autonomous agent patterns: ReAct, plan-and-execute, reflection, and self-correction loops."),
    "agent-evaluation": ("Agent Development", "Design and run agent evaluation pipelines: eval sets, automated scoring, human review, and CI integration."),
    "agent-memory-systems": ("Agent Development", "Implement agent memory: in-session state, long-term memory banks, retrieval augmentation, and memory management."),
    "agent-tool-builder": ("Agent Development", "Build and register agent tools: function definitions, input validation, error handling, and tool testing."),
    "agent-orchestrator": ("Agent Development", "Implement agent orchestration logic: intent routing, context passing, sub-agent invocation, and result merging."),
    "mcp-builder": ("Agent Development", "Build Model Context Protocol (MCP) servers: resource definitions, tool registration, and FastMCP patterns."),
    "mcp-tool-developer": ("Agent Development", "Develop MCP tools: schema design, handler implementation, testing, and deployment to Agent Registry."),

    # Category: Python / FastAPI
    "python-pro": ("Python / FastAPI", "Write idiomatic, production-quality Python: type hints, dataclasses, context managers, and best practices."),
    "python-patterns": ("Python / FastAPI", "Apply Python design patterns: factories, decorators, dependency injection, and protocol-based interfaces."),
    "python-fastapi-development": ("Python / FastAPI", "Build FastAPI applications: routing, dependency injection, middleware, background tasks, and OpenAPI docs."),
    "python-testing-patterns": ("Python / FastAPI", "Write comprehensive Python tests: pytest patterns, fixtures, mocking, parametrize, and coverage strategies."),
    "python-performance-optimization": ("Python / FastAPI", "Optimize Python performance: profiling, caching, vectorization, concurrency, and memory management."),
    "python-packaging": ("Python / FastAPI", "Package and distribute Python projects: pyproject.toml, setuptools, wheels, and publishing to PyPI."),
    "fastapi-basics": ("Python / FastAPI", "FastAPI fundamentals: path operations, request/response models, validation, and interactive API docs."),
    "fastapi-advanced": ("Python / FastAPI", "Advanced FastAPI patterns: lifespan, custom middleware, WebSockets, background tasks, and security."),
    "fastapi-routing": ("Python / FastAPI", "Organize FastAPI routes with routers, prefixes, tags, dependencies, and layered architecture patterns."),
    "pydantic-validation": ("Python / FastAPI", "Use Pydantic for data validation: model definitions, validators, custom types, and serialization."),
    "pydantic-settings": ("Python / FastAPI", "Manage application settings with pydantic-settings: env vars, .env files, and configuration hierarchies."),
    "async-python-patterns": ("Python / FastAPI", "Write async Python: asyncio, aiohttp, async context managers, task management, and concurrent patterns."),
    "uv-package-manager": ("Python / FastAPI", "Use uv for Python package management: workspaces, lockfiles, virtual environments, and scripting."),

    # Category: LangChain/LangGraph
    "langgraph": ("LangChain/LangGraph", "Build stateful multi-actor applications with LangGraph: nodes, edges, state management, and human-in-the-loop."),
    "langchain-architecture": ("LangChain/LangGraph", "Architect LangChain applications: chains, agents, retrievers, memory, callbacks, and production patterns."),
    "pydantic-ai": ("LangChain/LangGraph", "Build type-safe AI applications with pydantic-ai: agents, tools, structured outputs, and testing."),

    # Category: Deployment / DevOps
    "docker-expert": ("Deployment / DevOps", "Build optimized Docker images: multi-stage builds, layer caching, security scanning, and compose patterns."),
    "kubernetes-deployment": ("Deployment / DevOps", "Deploy to Kubernetes: manifests, Helm charts, resource management, rolling updates, and health checks."),
    "terraform-infrastructure": ("Deployment / DevOps", "Manage infrastructure as code with Terraform: modules, state management, workspaces, and GCP provider."),
    "devops-deploy": ("Deployment / DevOps", "Implement deployment workflows: blue-green, canary, rolling deployments, rollback strategies, and automation."),
    "cloud-architect": ("Deployment / DevOps", "Design cloud architectures: reliability, scalability, cost optimization, security, and well-architected frameworks."),
    "cloud-devops": ("Deployment / DevOps", "Apply cloud DevOps practices: infrastructure automation, configuration management, secret management, and GitOps."),
    "deployment-strategies": ("Deployment / DevOps", "Design and implement deployment strategies: feature flags, progressive delivery, and environment promotion."),
    "deployment-config": ("Deployment / DevOps", "Manage deployment configuration: environment variables, secrets, config maps, and environment parity."),
    "cicd-pipeline": ("Deployment / DevOps", "Build CI/CD pipelines: build stages, test automation, artifact management, and deployment gates."),
    "github-actions-templates": ("Deployment / DevOps", "Create reusable GitHub Actions templates: composite actions, workflow templates, and action marketplace."),
    "github-workflow-automation": ("Deployment / DevOps", "Automate GitHub workflows: matrix builds, conditional steps, environment secrets, and deployment workflows."),
    "gitops-workflow": ("Deployment / DevOps", "Implement GitOps: declarative infrastructure, reconciliation loops, drift detection, and ArgoCD/Flux patterns."),

    # Category: Observability
    "observability-engineer": ("Observability", "Design and implement full-stack observability: metrics, logs, traces, and alerting for production systems."),
    "observability-monitoring-basics": ("Observability", "Set up basic monitoring: Cloud Monitoring, uptime checks, alerting policies, and notification channels."),
    "observability-monitoring-advanced": ("Observability", "Advanced monitoring: custom metrics, SLO monitoring, anomaly detection, and multi-project dashboards."),
    "slo-implementation": ("Observability", "Define and implement SLOs: error budgets, SLI selection, alerting, and burn rate calculations."),
    "distributed-tracing": ("Observability", "Implement distributed tracing with OpenTelemetry: instrumentation, context propagation, and trace analysis."),
    "grafana-dashboards": ("Observability", "Build Grafana dashboards: panel types, PromQL queries, variables, alerting, and dashboard-as-code."),
    "prometheus-configuration": ("Observability", "Configure Prometheus: scrape configs, relabeling, recording rules, alerting rules, and federation."),

    # Category: Git / Code Review
    "git-pr-review": ("Git / Code Review", "Review pull requests: code quality assessment, security checks, performance analysis, and constructive feedback."),
    "git-pr-workflows-basics": ("Git / Code Review", "Manage basic PR workflows: branching strategies, commit messages, PR descriptions, and review requests."),
    "git-pr-workflows-advanced": ("Git / Code Review", "Advanced PR workflows: protected branches, CODEOWNERS, required checks, merge queues, and automation."),
    "git-pushing": ("Git / Code Review", "Manage git push workflows: remote tracking, force push safety, tags, and branch protection bypasses."),
    "commit": ("Git / Code Review", "Write high-quality git commits: conventional commits, atomic changes, co-authors, and commit hygiene."),
    "create-pr": ("Git / Code Review", "Create effective pull requests: descriptions, linked issues, screenshots, and checklist templates."),
    "code-review-excellence": ("Git / Code Review", "Conduct excellent code reviews: thoroughness, constructive tone, architecture feedback, and efficiency."),
    "code-reviewer": ("Git / Code Review", "Act as a code reviewer: identify bugs, anti-patterns, security issues, and improvement opportunities."),
    "pr-writer": ("Git / Code Review", "Write compelling PR descriptions: problem statement, solution approach, testing evidence, and migration notes."),

    # Category: Testing / Eval
    "evaluation": ("Testing / Eval", "Design evaluation frameworks for AI and software: metrics selection, dataset creation, and scoring systems."),
    "advanced-evaluation": ("Testing / Eval", "Advanced evaluation techniques: LLM-as-judge, pairwise comparison, online evaluation, and eval pipelines."),
    "testing-patterns": ("Testing / Eval", "Apply testing patterns: unit, integration, contract testing, test doubles, and test pyramid strategies."),
    "e2e-testing": ("Testing / Eval", "Implement end-to-end testing: Playwright, Selenium, API testing, test environments, and CI integration."),

    # Category: Claude / Prompt
    "claude-code-expert": ("Claude / Prompt", "Expert-level Claude Code usage: CLAUDE.md, custom commands, hooks, subagents, and workflow automation."),
    "claude-code-guide": ("Claude / Prompt", "Guide effective Claude Code sessions: context management, tool use, iteration patterns, and best practices."),
    "claude-api": ("Claude / Prompt", "Use the Claude API: authentication, models, messages API, streaming, tool use, and error handling."),
    "prompt-engineering": ("Claude / Prompt", "Engineer effective prompts: chain-of-thought, few-shot, system prompts, output formatting, and optimization."),
    "prompt-caching": ("Claude / Prompt", "Implement prompt caching: cache breakpoints, cost optimization, cache-aware prompt design, and TTL management."),

    # Category: Security
    "security-audit": ("Security", "Conduct security audits: OWASP checks, dependency scanning, secrets detection, IAM review, and threat modeling."),
    "security-auditor": ("Security", "Act as a security auditor: identify vulnerabilities, assess risk, recommend mitigations, and document findings."),
    "api-security-best-practices": ("Security", "Implement API security: authentication, authorization, rate limiting, input validation, and secure headers."),

    # Category: Bash / Linux
    "bash-pro": ("Bash / Linux", "Write professional bash scripts: error handling, argument parsing, logging, idempotency, and portability."),
    "bash-scripting": ("Bash / Linux", "Bash scripting fundamentals: variables, loops, conditionals, functions, process substitution, and pipelines."),
    "linux-troubleshooting": ("Bash / Linux", "Troubleshoot Linux systems: process management, networking, disk usage, logs, and performance analysis."),

    # Category: Architecture
    "software-architecture": ("Architecture", "Design software architectures: microservices, event-driven, hexagonal, and domain-driven design patterns."),
    "architecture": ("Architecture", "Apply architectural principles: SOLID, separation of concerns, dependency inversion, and scalability patterns."),
    "backend-architect": ("Architecture", "Architect backend systems: API design, data modeling, caching strategies, queue patterns, and reliability."),
    "api-design-principles": ("Architecture", "Design excellent APIs: REST conventions, versioning, pagination, error responses, and OpenAPI documentation."),

    # Category: Data / SQL
    "data-engineer": ("Data / SQL", "Build data pipelines: ETL/ELT, batch and streaming processing, data quality, and pipeline orchestration."),
    "sql-pro": ("Data / SQL", "Write advanced SQL: window functions, CTEs, query optimization, execution plans, and complex joins."),
    "postgresql": ("Data / SQL", "Work with PostgreSQL: schema design, indexing, JSONB, extensions, performance tuning, and replication."),

    # Category: LLM / ML
    "llm-evaluation": ("LLM / ML", "Evaluate LLM quality: benchmarks, automated metrics, human evaluation, and evaluation-driven development."),
    "llm-ops": ("LLM / ML", "Operate LLMs in production: model serving, versioning, A/B testing, monitoring, and cost optimization."),
    "ml-engineer": ("LLM / ML", "Apply ML engineering: training pipelines, model deployment, feature stores, and MLOps best practices."),

    # Category: Debugging
    "debugger": ("Debugging", "Debug complex issues: systematic isolation, hypothesis testing, log analysis, and root cause identification."),
    "debugging-strategies": ("Debugging", "Apply debugging strategies: binary search, rubber duck, divide-and-conquer, and time-travel debugging."),
    "systematic-debugging": ("Debugging", "Systematic debugging methodology: reproduce, isolate, hypothesis, verify, fix, and regression test."),
}


def make_skill(skill_id: str, category: str, description: str) -> str:
    title = skill_id.replace("-", " ").title()
    return textwrap.dedent(f"""\
        ---
        name: {skill_id}
        description: >
          {description}
        category: {category}
        ---

        # {title}

        ## Overview

        {description}

        ## When to Use This Skill

        Invoke this skill when the user asks about tasks related to **{title}**.

        ## Key Concepts

        - Core principles and patterns for {title}
        - Best practices and conventions
        - Common pitfalls and how to avoid them
        - Tooling and ecosystem recommendations

        ## Workflow

        1. Understand the user's goal and current context
        2. Apply domain-specific best practices for {title}
        3. Provide concrete, actionable guidance with code examples
        4. Validate the approach against production readiness criteria

        ## References

        - Official documentation and specifications
        - Community best practices
        - Related skills: {category}
    """)


created = 0
skipped = 0
errors = []

for skill_id, (category, description) in SKILLS.items():
    skill_dir = os.path.join(SKILLS_DIR, skill_id)
    skill_file = os.path.join(skill_dir, "SKILL.md")
    try:
        os.makedirs(skill_dir, exist_ok=True)
        if not os.path.exists(skill_file):
            with open(skill_file, "w") as f:
                f.write(make_skill(skill_id, category, description))
            created += 1
        else:
            skipped += 1
    except Exception as e:
        errors.append(f"{skill_id}: {e}")

print(f"Done. Created: {created}, Skipped (already existed): {skipped}, Errors: {len(errors)}")
if errors:
    for e in errors:
        print(f"  ERROR: {e}")
