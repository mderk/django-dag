"""
Examples of how to use the DAG (Directed Acyclic Graph) package.

This module provides practical examples of common usage patterns for the DAG package.
"""

from django.db import models
from apps.dag.models import DAGEntity, DAGLinksManager


# Example 1: Basic Category Hierarchy


class Category(models.Model, DAGEntity):
    """Example category model for hierarchical taxonomies."""

    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name


class CategoryLink(models.Model):
    """Link model for category hierarchies."""

    entity = models.ForeignKey(
        Category, on_delete=models.CASCADE, related_name="as_child"
    )
    parent = models.ForeignKey(
        Category, on_delete=models.CASCADE, related_name="as_parent"
    )
    path_id = models.IntegerField()
    depth = models.IntegerField()
    display_order = models.IntegerField(default=0)

    objects: DAGLinksManager[Category, "CategoryLink"] = DAGLinksManager[
        Category, "CategoryLink"
    ]()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["entity", "parent", "path_id"],
                name="category_link_unique_path_link",
            )
        ]
        indexes = [
            models.Index(fields=["entity", "parent"]),
            models.Index(fields=["path_id", "depth"]),
        ]


def create_category_hierarchy():
    """Example function that creates a sample category hierarchy."""
    # Create categories
    electronics = Category.objects.create(
        name="Electronics", description="Electronic devices and accessories"
    )
    computers = Category.objects.create(
        name="Computers", description="Desktop and laptop computers"
    )
    laptops = Category.objects.create(name="Laptops", description="Portable computers")
    gaming = Category.objects.create(
        name="Gaming Laptops", description="High-performance laptops for gaming"
    )
    business = Category.objects.create(
        name="Business Laptops", description="Laptops for business use"
    )

    # Create hierarchy
    CategoryLink.objects.add_link(computers, electronics, display_order=1)
    CategoryLink.objects.add_link(laptops, computers, display_order=1)
    CategoryLink.objects.add_link(gaming, laptops, display_order=1)
    CategoryLink.objects.add_link(business, laptops, display_order=2)

    # Direct link - creates a second path to gaming
    CategoryLink.objects.add_link(gaming, computers, display_order=2)

    return {
        "electronics": electronics,
        "computers": computers,
        "laptops": laptops,
        "gaming": gaming,
        "business": business,
    }


def traverse_hierarchy(categories):
    """Example function demonstrating traversal operations."""
    results = {}

    # Get all paths to gaming laptops
    gaming = categories["gaming"]
    paths = CategoryLink.objects.get_entity_paths(gaming)  # type: ignore
    results["gaming_paths"] = paths

    # Get direct parents of gaming laptops
    gaming_parents = CategoryLink.objects.get_parents(gaming)  # type: ignore
    results["gaming_parents"] = gaming_parents

    # Get all children of computers
    computers = categories["computers"]
    computer_children = CategoryLink.objects.get_children(computers)  # type: ignore
    results["computer_children"] = computer_children

    # Get all children of electronics (recursive traversal example)
    electronics = categories["electronics"]
    electronics_tree = CategoryLink.objects.get_full_hierarchy(electronics)
    results["electronics_tree"] = electronics_tree

    return results


def modify_hierarchy(categories):
    """Example function demonstrating modification operations."""
    # Remove the direct link from computers to gaming
    computers = categories["computers"]
    gaming = categories["gaming"]

    # This will remove the direct path but maintain the path through laptops
    affected_paths, new_links = CategoryLink.objects.remove_link(gaming, computers)  # type: ignore

    # Create a new top-level category
    tech = Category.objects.create(
        name="Technology", description="All technology products"
    )

    # Move electronics under technology
    electronics = categories["electronics"]
    CategoryLink.objects.add_link(electronics, tech)  # type: ignore

    # Get updated paths
    updated_paths = CategoryLink.objects.get_entity_paths(gaming)  # type: ignore

    return {
        "affected_paths": affected_paths,
        "new_links": new_links,
        "updated_paths": updated_paths,
    }


# Example 2: Organization Chart


class Employee(models.Model, DAGEntity):
    """Example employee model for organization charts."""

    name = models.CharField(max_length=100)
    title = models.CharField(max_length=100)
    email = models.EmailField()

    def __str__(self):
        return f"{self.name} ({self.title})"


class ReportingLink(models.Model):
    """Link model for reporting relationships."""

    entity = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name="reports_to"
    )
    parent = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name="manages"
    )
    path_id = models.IntegerField()
    depth = models.IntegerField()
    start_date = models.DateField(auto_now_add=True)

    objects = DAGLinksManager[Employee, "ReportingLink"]()  # type: ignore

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["entity", "parent", "path_id"],
                name="reporting_link_unique_path_link",
            )
        ]
        indexes = [
            models.Index(fields=["entity", "parent"]),
            models.Index(fields=["path_id", "depth"]),
        ]


def create_org_chart():
    """Example function that creates a sample organization chart."""
    # Create employees
    ceo = Employee.objects.create(
        name="Jane Smith", title="CEO", email="jane@example.com"
    )
    cto = Employee.objects.create(
        name="Mike Johnson", title="CTO", email="mike@example.com"
    )
    cfo = Employee.objects.create(
        name="Sarah Williams", title="CFO", email="sarah@example.com"
    )
    engineering_dir = Employee.objects.create(
        name="David Brown", title="Engineering Director", email="david@example.com"
    )
    senior_dev = Employee.objects.create(
        name="Lisa Chen", title="Senior Developer", email="lisa@example.com"
    )

    # Create reporting structure
    ReportingLink.objects.add_link(cto, ceo)  # type: ignore
    ReportingLink.objects.add_link(cfo, ceo)  # type: ignore
    ReportingLink.objects.add_link(engineering_dir, cto)  # type: ignore
    ReportingLink.objects.add_link(senior_dev, engineering_dir)  # type: ignore

    return {
        "ceo": ceo,
        "cto": cto,
        "cfo": cfo,
        "engineering_dir": engineering_dir,
        "senior_dev": senior_dev,
    }


def get_reporting_chain(employee):
    """Get the complete reporting chain for an employee."""
    paths = ReportingLink.objects.get_entity_paths(employee)  # type: ignore
    if not paths:
        return []

    # Get the first path (there should typically be only one in an org chart)
    path = paths[0][0]

    # Load all employees in the path
    employee_ids = path
    employees = Employee.objects.filter(id__in=employee_ids).in_bulk()

    # Return employees in path order
    return [employees[emp_id] for emp_id in path if emp_id in employees]
