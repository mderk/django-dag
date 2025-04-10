# Django DAG (Directed Acyclic Graph) Package

## Overview

The DAG package provides a robust implementation for managing directed acyclic graphs in Django applications. It allows for efficient modeling and traversal of hierarchical data structures while maintaining complete path information.

## Key Features

-   **Complete Path Management**: Tracks full paths from root to leaf nodes
-   **Relationship Handling**: Easy creation and removal of links with automatic path updates
-   **Concurrency Support**: Thread-safe operations with atomic transactions
-   **Performance Optimized**: Efficient path handling for large graphs
-   **Flexible API**: Support for custom link properties and filtering
-   **Property Preservation**: Custom link properties are maintained during graph modifications

## Core Components

### DAGEntity Protocol

Defines the required interface for entities that can participate in the graph:

```python
class DAGEntity:
    """Protocol defining required interface for entities in the DAG"""
    id: models.IntegerField
```

### PathId Model

Manages unique path identifiers for each content type:

```python
class PathId(models.Model):
    content_type = models.OneToOneField(ContentType, on_delete=models.CASCADE, primary_key=True)
    value = models.IntegerField()
```

### AbstractDAGLink

Abstract base class for link models that connect entities:

```python
class AbstractDAGLink(models.Model, Generic[EntityT]):
    path_id = models.IntegerField(db_index=True)
    depth = models.IntegerField()

    # Must be implemented by subclasses
    entity: models.ForeignKey
    parent: models.ForeignKey
```

### DAGLinksManager

The core manager class that handles all DAG operations:

```python
class DAGLinksManager(models.Manager, Generic[EntityT, LinkModelT]):
    """
    Generic Manager for handling DAG relationships.
    """
    # Methods for managing and traversing the graph
```

## Implementation Details

### Path Tracking

Each path in the graph is assigned a unique `path_id`. Links within the same path share this ID, with a `depth` value indicating their position in the path. This allows for:

1. Efficient traversal of complete paths
2. Maintaining path integrity during modifications
3. Handling multiple paths to the same entity

### Link Management

When adding or removing links, the system maintains path integrity by:

1. Creating new paths as needed
2. Splitting paths at branch points
3. Merging paths when appropriate
4. Rebuilding affected paths after link removal

### Property Preservation

The DAG system intelligently preserves custom link properties when the graph structure changes:

1. When creating new paths during node addition, properties from existing links are carried over
2. During path splitting, each link maintains its original properties
3. When removing links, properties of downstream links are preserved in rebuilt paths
4. This allows for custom metadata (e.g., weights, labels, timestamps) to persist through graph modifications

### Atomic Operations

All operations that modify the graph structure use database transactions to ensure data consistency, even in concurrent environments.

## Usage Examples

### 1. Define Your Entity and Link Models

```python
from django.db import models
from apps.dag.models import DAGEntity, AbstractDAGLink, DAGLinksManager

class Category(models.Model, DAGEntity):
    name = models.CharField(max_length=100)

class CategoryLink(AbstractDAGLink["Category"]):
    entity = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='as_child')
    parent = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='as_parent')

    # Custom properties - will be preserved during graph changes
    display_order = models.IntegerField(default=0)
    is_featured = models.BooleanField(default=False)

    objects = DAGLinksManager[Category, "CategoryLink"]()

    class Meta(AbstractDAGLink.Meta):
        constraints = [*AbstractDAGLink.Meta.constraints]
```

### 2. Creating Links

```python
# Create categories
electronics = Category.objects.create(name="Electronics")
computers = Category.objects.create(name="Computers")
laptops = Category.objects.create(name="Laptops")

# Create hierarchy with custom properties
CategoryLink.objects.add_link(computers, electronics, display_order=1, is_featured=True)  # Computers under Electronics
CategoryLink.objects.add_link(laptops, computers, display_order=2)     # Laptops under Computers

# Add a new direct path - this will maintain properties of existing links
CategoryLink.objects.add_link(laptops, electronics, display_order=5)  # Direct link from Electronics to Laptops
```

### 3. Traversing the Graph

```python
# Get all parents of an entity
parents = CategoryLink.objects.get_parents(laptops)  # Returns [computers, electronics]

# Get all children of an entity
children = CategoryLink.objects.get_children(electronics)  # Returns [computers, laptops]

# Get complete paths to an entity
paths = CategoryLink.objects.get_entity_paths(laptops)
# Returns [([electronics.id, computers.id, laptops.id], True, path_id), ([electronics.id, laptops.id], True, path_id)]
```

### 4. Removing Links

```python
# Remove a link and handle path updates
original_paths, new_links = CategoryLink.objects.remove_link(laptops, computers)

# Properties on the direct Electronics -> Laptops link are preserved
```

### 5. Custom Link Properties

```python
# Add link with custom properties
CategoryLink.objects.add_link(laptops, computers, display_order=1, is_featured=True, metadata={'source': 'import'})

# These properties will be preserved even when the graph structure changes
```

## Best Practices

1. **Entity Design**:

    - Keep entity models focused on data attributes
    - Let the DAG system handle relationship logic

2. **Performance Considerations**:

    - For very large graphs, consider implementing caching for frequently accessed paths
    - Use database indexes for fields used in frequent queries

3. **Integrity Management**:

    - Implement periodic integrity checks for large, complex graphs
    - Handle link removal carefully to maintain consistency

4. **Concurrency**:

    - The system handles concurrency internally through transactions
    - For high-concurrency environments, consider implementing additional application-level locking

5. **Custom Properties**:

    - Use custom properties to store metadata about relationships
    - These properties will be automatically preserved during graph operations
    - For complex property inheritance rules, consider implementing custom logic

6. **Migration Safety**:
    - When migrating databases with large DAGs, ensure proper backup procedures
    - Test migrations thoroughly in staging environments

## Testing

### Setup Requirements

For testing the DAG implementation, you need to properly configure your test environment:

1. **Include the Test App Configuration**:
   To properly test the DAG implementation, you must include the DAG test app configuration in your project's `INSTALLED_APPS`:

    ```python
    # In settings.py or test settings
    INSTALLED_APPS = [
        # ... other apps
        "apps.dag",
        "apps.dag.tests.apps.DAGTestConfig",  # Required for DAG tests
    ]
    ```

    This ensures that test models are properly registered and database tables are created during test runs.

2. **Conditional Inclusion**:
   For a cleaner approach, you can conditionally include the test app only when running tests:

    ```python
    # In settings.py
    import sys

    INSTALLED_APPS = [
        # ... other apps
        "apps.dag",
    ]

    if 'test' in sys.argv:
        INSTALLED_APPS += [
            "apps.dag.tests.apps.DAGTestConfig",
        ]
    ```

### Test Scenarios

For testing DAG implementations:

1. Create mock entity and link models
2. Test basic link creation and removal
3. Test path traversal and integrity
4. Test complex scenarios like branching and merging
5. Test property preservation during graph modifications
6. Test concurrency with multiple threads

## Use Cases

This DAG implementation is ideal for:

-   Organizational hierarchies
-   Category systems
-   Document management
-   Process workflows
-   Any tree-like structure requiring complete path information

## Limitations

-   Very deep hierarchies (1000+ levels) may impact performance
-   High-concurrency environments with many writes to the same paths may experience contention
-   Path queries return complete paths, which may be memory-intensive for very large graphs

## Future Improvements

-   Query optimization for partial path retrieval
-   Caching layer for frequently accessed paths
-   Bulk operations for adding/removing multiple links
-   Custom property inheritance rules
