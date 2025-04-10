# Django DAG

A robust implementation of Directed Acyclic Graph (DAG) structure for Django applications.

## Installation

1. Add the app to your Django project's `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    # ...
    'apps.dag',
    # ...
]
```

2. Run migrations:

```bash
python manage.py migrate dag
```

## Quick Start

### 1. Define your models

```python
from django.db import models
from apps.dag.models import DAGEntity, AbstractDAGLink, DAGLinksManager

class Category(models.Model, DAGEntity):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name

class CategoryLink(AbstractDAGLink["Category"]):
    entity = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='as_child')
    parent = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='as_parent')

    objects = DAGLinksManager[Category, "CategoryLink"]()

    class Meta(AbstractDAGLink.Meta):
        constraints = [*AbstractDAGLink.Meta.constraints]
```

### 2. Create and manage your hierarchy

```python
# Create some entities
root = Category.objects.create(name="Root")
child1 = Category.objects.create(name="Child 1")
child2 = Category.objects.create(name="Child 2")
grandchild = Category.objects.create(name="Grandchild")

# Build the hierarchy
CategoryLink.objects.add_link(child1, root)
CategoryLink.objects.add_link(child2, root)
CategoryLink.objects.add_link(grandchild, child1)

# Get all paths to an entity
paths = CategoryLink.objects.get_entity_paths(grandchild)
# Returns paths from root to grandchild

# Get direct parents
parents = CategoryLink.objects.get_parents(grandchild)  # Returns [child1]

# Get direct children
children = CategoryLink.objects.get_children(root)  # Returns [child1, child2]
```

## Features

-   Complete path tracking from root to leaf nodes
-   Efficient path management with unique path IDs
-   Support for multiple paths to the same entity
-   Thread-safe operations with atomic transactions
-   Highly optimized for performance with large hierarchies
-   Custom property preservation during graph modifications

## Documentation

For full documentation, see the [doc.md](doc.md) file.

## Testing

### Required Setup

To run the tests for this app, you need to add the test app configuration to your project's `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    # ... existing apps
    'apps.dag',
    'apps.dag.tests.apps.DAGTestConfig',  # Required for testing
]
```

This ensures that the test models are properly registered and their database tables are created during test runs.

Alternatively, you can conditionally include the test app only when running tests:

```python
import sys

INSTALLED_APPS = [
    # ... existing apps
    'apps.dag',
]

if 'test' in sys.argv:
    INSTALLED_APPS += [
        'apps.dag.tests.apps.DAGTestConfig',
    ]
```

### Running Tests

Run the tests with:

```bash
python manage.py test apps.dag
```

If you encounter database-related issues, you can use the `--keepdb` flag to reuse the test database:

```bash
python manage.py test apps.dag --keepdb
```

## License

This project is licensed under the MIT License - see the LICENSE file for details.
