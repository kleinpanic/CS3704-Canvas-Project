# Architecture

The Canvas TUI follows a **Model-View-Controller (MVC)** architecture with a **shared domain core** designed for future parity with a browser extension.

## Design Philosophy

- **Offline-first**: SQLite cache enables reliable offline operation
- **Shared logic**: Business rules in reusable domain layer
- **Platform adapters**: UI and storage specific to each platform
- **Observable**: Structured logging and metrics for maintenance

## Architecture Diagrams

### High-level System Design

![Complex Architecture](assets/architecture/complex-architecture.svg)

*Component relationships and data flow*

### Sync Sequence

![Sync Flow](assets/architecture/sync-flow.svg)

*Data refresh and synchronization flow*

## Core Patterns

### MVC Pattern

| Layer | Components | Files |
|-------|------------|-------|
| **Model** | API client, state management, cache | `api.py`, `state.py`, `cache.py`, `models.py` |
| **View** | Textual screens and widgets | `screens/`, `widgets/` |
| **Controller** | App orchestration, routing | `app.py`, `cli.py` |

### Command Pattern

User actions are encapsulated as commands:
- `RefreshDataCommand` — sync with Canvas API
- `SwitchScreenCommand` — navigate between views
- `ApplyFilterCommand` — filter displayed data

This decouples UI widgets from application logic.

### Repository Pattern

Data access is abstracted through the API gateway and cache:
- Transparent offline/online operation
- Consistent error handling
- Rate limiting and retry logic

## Component Overview

### Canvas API Gateway

- Authentication and session management
- Request normalization
- Rate limiting (429 handling)
- Retry with exponential backoff

### Offline Cache

- SQLite persistence layer
- Full + incremental sync strategies
- Cache invalidation policies
- Conflict resolution

### Textual TUI

- Dashboard with course overview
- Assignment detail screens
- Grades with trend visualization
- File browser and downloads
- Calendar with ICS export

## Source Files

- Architecture diagrams: `docs/architecture/*.mmd`
- SVG exports: `docs/assets/architecture/*.svg`
- Wiki documentation: [Architecture Overview](https://github.com/kleinpanic/CS3704-Canvas-Project/wiki/Architecture-Overview)

## Future: Browser Extension

The shared domain core enables:
- Same business logic for TUI and extension
- Platform-specific UI adapters
- Shared test suite for core logic
- Feature parity without duplication
