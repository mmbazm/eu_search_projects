"""
Visualization utilities for European project data.

This module contains reusable functions for generating interactive
charts and network visualizations from project data.

The functions expect a Python list of project dictionaries, typically
returned by the backend. Each project may contain information such as:

    - acronym
    - title
    - start_date
    - end_date
    - overall_budget
    - eu_contribution
    - participants

Plotly is used for interactive charts and PyVis is used for
interactive network graphs.

Example:

    from helpers.charts import plot_budget_vs_duration

    fig = plot_budget_vs_duration(projects)
    st.plotly_chart(fig, use_container_width=True)
"""


from datetime import datetime
from collections import defaultdict

import plotly.graph_objects as go
from pyvis.network import Network
import matplotlib.pyplot as plt
from pyvis.network import Network
import plotly.graph_objects as go
from itertools import combinations
import matplotlib.colors as mcolors
from matplotlib import colormaps as mpl_colormaps

def create_collaboration_graph(
    projects,
    height="700px",
    width="100%",
    directed=False,
):
    """
    Create an interactive PyVis collaboration graph.

    Nodes:
        Organizations / participants

    Edges:
        Two organizations are connected when they participate
        in the same project.

    Edge weight:
        Number of projects shared by the two organizations.

    Parameters
    ----------
    projects : list[dict]
        List of projects. Each project must contain a
        "participants" list.

    Returns
    -------
    Network
        PyVis interactive network.
    """

    # ---------------------------------------------------------
    # 1. Count projects for each organization
    # ---------------------------------------------------------

    organization_projects = defaultdict(set)
    organization_acronyms = defaultdict(set)
    organizations = {}


    for project in projects:
        project_id = project.get("id")

        if not project_id:
            continue

        for participant in project.get("participants", []):
            name = participant.get("legalName")

            if not name:
                continue

            organization_projects[name].add(project_id)
            acronym = project.get("acronym")
            if acronym:
                organization_acronyms[name].add(acronym)

            organizations[name] = participant


    # ---------------------------------------------------------
    # 2. Count common projects between organizations
    # ---------------------------------------------------------

    collaboration_count = defaultdict(int)

    organization_names = list(organization_projects.keys())

    for i, org_a in enumerate(organization_names):
        for org_b in organization_names[i + 1:]:

            common_projects = (
                organization_projects[org_a]
                & organization_projects[org_b]
            )

            if common_projects:
                collaboration_count[(org_a, org_b)] = len(common_projects)

    # ---------------------------------------------------------
    # 3. Create PyVis network
    # ---------------------------------------------------------

    net = Network(
        height=height,
        width=width,
        directed=directed,
        bgcolor="#ffffff",
        font_color="#222222",
        notebook=False,
    )

    # Enable physics
    net.set_options("""
    {
      "physics": {
        "enabled": true,
        "solver": "forceAtlas2Based",
        "forceAtlas2Based": {
          "gravitationalConstant": -50,
          "centralGravity": 0.01,
          "springLength": 150,
          "springConstant": 0.08,
          "damping": 0.4
        },
        "minVelocity": 0.75
      },
      "interaction": {
        "hover": true,
        "navigationButtons": true,
        "keyboard": true
      }
    }
    """)

    # ---------------------------------------------------------
    # 4. Add organization nodes
    # ---------------------------------------------------------

    for name, participant in organizations.items():

        country = participant.get("country") or "Unknown"
        city = participant.get("city") or ""
        role = participant.get("role") or ""

        project_count = len(
            organization_projects[name]
        )

        # Larger node = more projects
        size = 10 + project_count * 3

        project_acronyms = sorted(organization_acronyms[name])

        title = (
            f"{name}\n"
            f"Country: {country}\n"
            f"City: {city}\n"
            f"Projects: {project_count}\n"
            f"Involved in: {', '.join(project_acronyms)}"
        )
        net.add_node(
            name,
            label=name,
            title=title,
            size=size,
            color="#4F81BD",
        )

    # ---------------------------------------------------------
    # 5. Add collaboration edges
    # ---------------------------------------------------------

    for (org_a, org_b), count in collaboration_count.items():

        # Make strong collaborations visually thicker
        width = 1 + count * 2

        title = (
            f"Common projects: {count}\n"
            f"- {org_a}\n"
            f"- {org_b}"
        )

        net.add_edge(
            org_a,
            org_b,
            value=count,
            width=width,
            title=title,
            label=str(count),
        )

    return net

def create_country_collaboration_graph(
    projects,
    min_projects=1,
    top_n=20,
):
    """
    Create a PyVis country collaboration network for the top countries.

    Ranking:
        Countries are ranked by the number of distinct projects.

    Node:
        Country

    Edge:
        Two countries participating in the same project.

    Edge thickness:
        Number of common projects.

    Edge tooltip:
        Project acronyms.
    """

    # ---------------------------------------------------------
    # Country -> projects
    # ---------------------------------------------------------

    country_projects = defaultdict(set)

    for project in projects:
        acronym = project.get("acronym")

        if not acronym:
            continue

        countries = {
            participant.get("country")
            for participant in project.get("participants", [])
            if participant.get("country")
        }

        for country in countries:
            country_projects[country].add(acronym)

    # ---------------------------------------------------------
    # Select the top countries
    # ---------------------------------------------------------

    top_countries = {
        country
        for country, acronyms in sorted(
            country_projects.items(),
            key=lambda item: len(item[1]),
            reverse=True,
        )[:top_n]
    }

    # ---------------------------------------------------------
    # Country pairs -> common projects
    # ---------------------------------------------------------

    collaboration = defaultdict(set)

    for project in projects:
        acronym = project.get("acronym")

        if not acronym:
            continue

        countries = sorted({
            participant.get("country")
            for participant in project.get("participants", [])
            if participant.get("country")
            and participant.get("country") in top_countries
        })

        for i in range(len(countries)):
            for j in range(i + 1, len(countries)):
                country_a = countries[i]
                country_b = countries[j]

                collaboration[(country_a, country_b)].add(acronym)

    # ---------------------------------------------------------
    # Create network
    # ---------------------------------------------------------

    net = Network(
        height="700px",
        width="100%",
        bgcolor="#ffffff",
        font_color="#222222",
        directed=False,
    )

    net.set_options("""
    {
      "physics": {
        "enabled": true,
        "solver": "forceAtlas2Based",
        "forceAtlas2Based": {
          "gravitationalConstant": -80,
          "centralGravity": 0.01,
          "springLength": 180,
          "springConstant": 0.05,
          "damping": 0.4
        },
        "minVelocity": 0.75
      },
      "interaction": {
        "hover": true,
        "navigationButtons": true,
        "keyboard": true
      }
    }
    """)

    # ---------------------------------------------------------
    # Nodes
    # ---------------------------------------------------------

    # Precompute the range across ALL top countries so colors are normalized
    # consistently (not per-node, which would make every node look "hottest").
    project_counts = [len(country_projects[c]) for c in top_countries]
    min_count, max_count = min(project_counts), max(project_counts)
    if min_count == max_count:
        max_count = min_count + 1  # avoid a zero-width range if every country ties

    cmap = mpl_colormaps["Oranges"]  # yellow (few projects) -> red (many); swap for any matplotlib colormap
    norm = mcolors.Normalize(vmin=min_count, vmax=max_count)

    for country in sorted(top_countries):
        acronyms = country_projects[country]
        project_count = len(acronyms)

        size = 5 + project_count * 1.5
        color = mcolors.to_hex(cmap(norm(project_count)))

        net.add_node(
            country,
            label=country,
            size=size,
            color=color,
            font={
                "color": "white",
                "size": 14
            },
            title=(
                f"{country}\n"
                f"Projects: {project_count}\n"
                f"Projects: {', '.join(sorted(acronyms))}"
            ),
        )

    # ---------------------------------------------------------
    # Edges
    # ---------------------------------------------------------

    for (country_a, country_b), acronyms in collaboration.items():
        common_projects = len(acronyms)

        if common_projects < min_projects:
            continue

        width = 2#1 + common_projects * 1.5

        net.add_edge(
            country_a,
            country_b,
            width=width,
            color="#999999",
            title=(
                f"{country_a} ↔ {country_b}\n"
                f"Common projects: {common_projects}\n"
                f"{', '.join(sorted(acronyms))}"
            ),
        )

    return net

def plot_budget_vs_duration(projects, top_n=20):
    project_data = []

    for project in projects:
        acronym = project.get("acronym") or "N/A"
        title = project.get("title") or "Untitled"

        start_date = project.get("start_date")
        end_date = project.get("end_date")
        budget = project.get("overall_budget")

        if not start_date or not end_date or budget is None:
            continue

        try:
            start = datetime.fromisoformat(start_date)
            end = datetime.fromisoformat(end_date)

            budget = float(
                str(budget)
                .replace(",", "")
                .replace("€", "")
                .strip()
            )
        except (ValueError, TypeError):
            continue

        duration_months = (end - start).days / 30.44

        if duration_months < 0:
            continue

        total_contribution = 0.0

        for participant in project.get("participants", []):
            contribution = participant.get("eu_contribution")

            if contribution is None:
                continue

            try:
                total_contribution += float(
                    str(contribution)
                    .replace(",", "")
                    .replace("€", "")
                    .strip()
                )
            except (ValueError, TypeError):
                continue

        project_data.append({
            "duration": duration_months,
            "budget": budget,
            "contribution": total_contribution,
            "acronym": acronym,
            "title": title,
        })

    # Sort by budget-duration combination and keep the top 20.
    # This uses normalized ranks so budget and duration contribute equally.
    project_data.sort(
        key=lambda project: (
            project["budget"],
            project["duration"],
        ),
        reverse=True,
    )

    top_projects = project_data[:top_n]

    if not top_projects:
        raise ValueError("No valid projects available for plotting.")

    durations = [project["duration"] for project in top_projects]
    budgets = [project["budget"] for project in top_projects]
    contributions = [project["contribution"] for project in top_projects]
    acronyms = [project["acronym"] for project in top_projects]
    titles = [project["title"] for project in top_projects]

    fig = go.Figure()

    fig.add_trace(
        go.Scatter(
            x=durations,
            y=budgets,
            mode="markers+text",
            text=acronyms,
            textposition="top center",
            marker=dict(
                size=[
                    max(10, min(50, contribution / 100000))
                    for contribution in contributions
                ],
                color="#F59E0B",
                opacity=0.75,
                line=dict(
                    width=1,
                    color="#B45309",
                ),
            ),
            customdata=list(
                zip(
                    acronyms,
                    titles,
                    contributions,
                )
            ),
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "%{customdata[1]}<br>"
                "Duration: %{x:.1f} months<br>"
                "Overall budget: €%{y:,.0f}<br>"
                "EU contribution: €%{customdata[2]:,.0f}"
                "<extra></extra>"
            ),
        )
    )

    fig.update_layout(
        title=f"Top {len(top_projects)} Projects by Budget and Duration",
        xaxis_title="Project duration (months)",
        yaxis_title="Overall budget (€)",
        height=650,
        template="plotly_white",
    )

    return fig

def plot_project_similarity(projects):
    """
    Create a project similarity heatmap based on shared participants.

    Similarity = Jaccard similarity:
        intersection / union

    Each cell represents similarity between two projects.
    """

    project_participants = {}
    project_acronyms = []

    for project in projects:

        acronym = project.get("acronym")

        if not acronym:
            continue

        participants = set()

        for participant in project.get("participants", []):

            name = participant.get("legalName")

            if name:
                participants.add(name)

        project_participants[acronym] = participants
        project_acronyms.append(acronym)

    # ---------------------------------------------------------
    # Calculate similarity matrix
    # ---------------------------------------------------------

    matrix = []

    for acronym_a in project_acronyms:

        row = []

        participants_a = project_participants[acronym_a]

        for acronym_b in project_acronyms:

            participants_b = project_participants[acronym_b]

            intersection = len(
                participants_a & participants_b
            )

            union = len(
                participants_a | participants_b
            )

            similarity = (
                intersection / union
                if union
                else 0
            )

            row.append(similarity)

        matrix.append(row)

    # ---------------------------------------------------------
    # Heatmap
    # ---------------------------------------------------------

    fig = go.Figure(
        data=go.Heatmap(
            z=matrix,
            x=project_acronyms,
            y=project_acronyms,

            colorscale=[
                [0.0, "#FFF7ED"],
                [0.25, "#FED7AA"],
                [0.5, "#FDBA74"],
                [0.75, "#F97316"],
                [1.0, "#C2410C"],
            ],

            zmin=0,
            zmax=1,

            text=[
                [
                    f"{value * 100:.0f}%"
                    for value in row
                ]
                for row in matrix
            ],

            texttemplate="%{text}",

            hovertemplate=(
                "<b>%{y}</b> ↔ <b>%{x}</b><br>"
                "Similarity: %{z:.1%}"
                "<extra></extra>"
            ),

            colorbar=dict(
                title="Similarity"
            ),
        )
    )

    fig.update_layout(
        title="Project Similarity Based on Shared Participants",
        xaxis_title="Project",
        yaxis_title="Project",
        height=700,
        template="plotly_white",
    )

    return fig

def plot_project_timeline(
    projects,
    start_year=2015,
    end_year=2026,
    figsize=(14, 4),
    color="#789fe7",
    title="Top 20 Longest Projects",
    top_n=20,
):
    """
    Plot the top projects with the longest durations.

    Projects must contain:
        - title
        - start_date: YYYY-MM-DD
        - end_date: YYYY-MM-DD
        - optionally acronym

    Parameters
    ----------
    projects : list[dict]
        List of project dictionaries.

    start_year : int
        First year displayed on the timeline.

    end_year : int
        Last year displayed on the timeline.

    figsize : tuple
        Figure width and height.

    color : str
        Project-bar color.

    title : str
        Chart title.

    top_n : int
        Number of longest projects to display.

    Returns
    -------
    matplotlib.figure.Figure
        The generated figure.
    """

    # ---------------------------------------------------------
    # Parse dates and calculate duration
    # ---------------------------------------------------------

    valid_projects = []

    for project in projects:
        start_date = project.get("start_date")
        end_date = project.get("end_date")

        if not start_date or not end_date:
            continue

        try:
            start = datetime.fromisoformat(start_date)
            end = datetime.fromisoformat(end_date)
        except (TypeError, ValueError):
            continue

        duration = (end - start).days

        # Ignore invalid projects with negative duration
        if duration < 0:
            continue

        project_copy = project.copy()
        project_copy["_start"] = start
        project_copy["_end"] = end
        project_copy["_duration"] = duration

        valid_projects.append(project_copy)

    # ---------------------------------------------------------
    # Select the top 20 longest projects
    # ---------------------------------------------------------

    longest_projects = sorted(
        valid_projects,
        key=lambda project: project["_duration"],
        reverse=True,
    )[:top_n]

    if not longest_projects:
        raise ValueError("No valid projects with usable start and end dates.")

    # ---------------------------------------------------------
    # Create figure
    # ---------------------------------------------------------

    fig, ax = plt.subplots(figsize=figsize)

    for i, project in enumerate(longest_projects):
        start = project["_start"]
        end = project["_end"]
        duration = project["_duration"]

        ax.barh(
            y=i,
            width=duration,
            left=start,
            height=0.45,
            color=color,
            alpha=0.85,
        )

        label = project.get("acronym") or project.get("title", "Unknown project")

        duration_months = duration / 30.4375

        ax.text(
            start,
            i,
            f"  {label} ({duration_months:.1f} months)",
            va="center",
            ha="left",
            fontsize=10,
            color="#222222",
        )

    # First project appears at the top
    ax.invert_yaxis()

    # Hide Y axis
    ax.set_yticks([])

    # Timeline limits
    ax.set_xlim(
        datetime(start_year, 1, 1),
        datetime(end_year + 1, 1, 1),
    )

    # Show years
    years = range(start_year, end_year + 1)

    ax.set_xticks([
        datetime(year, 1, 1)
        for year in years
    ])

    ax.set_xticklabels(years)

    # Grid
    ax.grid(
        axis="x",
        linestyle="--",
        alpha=0.25,
    )

    # Remove unnecessary borders
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)

    ax.set_title(title, loc="left", fontsize=13, color="#333333")

    plt.tight_layout()

    return fig


def plot_project_budgets(projects):
    """
    Create a project budget chart for the top 20 projects by overall budget,
    showing:
    - Overall budget
    - EU contribution
    """

    project_data = []

    for project in projects:
        acronym = project.get("acronym") or project.get("title") or "Unknown"

        overall = project.get("overall_budget")
        eu = project.get("eu_contribution_amount")

        if overall is None or eu is None:
            continue

        # Handle values such as:
        # "7,500,000"
        # "7500000"
        # 7500000
        overall = float(str(overall).replace(",", ""))
        eu = float(str(eu).replace(",", ""))

        project_data.append(
            (acronym, overall, eu)
        )

    # Keep only the top 20 projects by overall budget
    project_data = sorted(
        project_data,
        key=lambda x: x[1],
        reverse=True
    )[:20]

    labels = [x[0] for x in project_data]
    overall_budgets = [x[1] for x in project_data]
    eu_contributions = [x[2] for x in project_data]

    fig = go.Figure()

    fig.add_trace(
        go.Bar(
            name="Overall budget",
            x=labels,
            y=overall_budgets,
            marker_color="#0B59F4"
        )
    )

    fig.add_trace(
        go.Bar(
            name="EU contribution",
            x=labels,
            y=eu_contributions,
            marker_color="#F59E0B"
        )
    )

    fig.update_layout(
        title="Top 20 Projects by Overall Budget",
        xaxis_title="Project",
        yaxis_title="Amount (€)",
        barmode="group",
        hovermode="x unified",
    )

    return fig

def plot_projects_per_participant(projects, top_n=None):
    """
    Show the number of projects per participant.
    """

    participant_projects = defaultdict(set)

    for project in projects:
        project_id = project.get("id")

        if not project_id:
            continue

        for participant in project.get("participants", []):
            name = participant.get("legalName")

            if name:
                participant_projects[name].add(project_id)

    # Sort by number of projects
    participants = sorted(
        participant_projects.items(),
        key=lambda x: len(x[1]),
        reverse=True,
    )

    # Optional: only show top N
    if top_n:
        participants = participants[:top_n]

    names = [p[0] for p in participants]
    counts = [len(p[1]) for p in participants]

    # Shorter labels for the chart
    labels = [
        name if len(name) <= 35 else name[:32] + "..."
        for name in names
    ]

    fig = go.Figure(
        go.Bar(
            x=counts,
            y=labels,
            orientation="h",
            marker_color="#C71065",
            text=counts,
            textposition="outside",
            hovertext=names,
            hovertemplate=(
                "<b>%{hovertext}</b><br>"
                "Projects: %{x}"
                "<extra></extra>"
            ),
        )
    )

    fig.update_layout(
        title="Number of projects per participant",
        xaxis_title="Number of projects",
        yaxis_title="",
        yaxis=dict(
            autorange="reversed"
        ),
        height=max(400, len(labels) * 35),
        margin=dict(l=250),
    )

    return fig

def plot_eu_contribution_by_country(projects):
    """
    Sum participant EU contributions by country.

    X-axis: country
    Y-axis: total EU contribution
    """

    country_totals = defaultdict(float)

    for project in projects:

        for participant in project.get("participants", []):

            country = participant.get("country")
            contribution = participant.get("eu_contribution")

            if not country or contribution is None:
                continue

            try:
                contribution = float(contribution)
            except (ValueError, TypeError):
                continue

            country_totals[country] += contribution

    # Sort by total contribution, highest first
    country_data = sorted(
        country_totals.items(),
        key=lambda item: item[1],
        reverse=True,
    )

    countries = [item[0] for item in country_data]
    totals = [item[1] for item in country_data]

    # Create chart
    fig = go.Figure(
        go.Bar(
            x=countries,
            y=totals,
            marker_color="#F59E0B",
            text=[f"€{value:,.0f}" for value in totals],
            textposition="outside",
            hovertemplate=(
                "<b>%{x}</b><br>"
                "EU contribution: €%{y:,.2f}"
                "<extra></extra>"
            ),
        )
    )

    fig.update_layout(
        title="EU Contribution by Country",
        xaxis_title="Country",
        yaxis_title="Total EU Contribution (€)",
        height=550,
    )

    return fig


def plot_contribution_per_participant(projects, top_n=None):
    """
    Calculate total EU contribution per participant
    across the given projects.

    X/Y:
        Horizontal bar chart:
        participant -> total EU contribution
    """

    participant_totals = defaultdict(float)

    for project in projects:

        for participant in project.get("participants", []):

            name = participant.get("legalName")
            contribution = participant.get("eu_contribution")

            if not name or contribution is None:
                continue

            try:
                contribution = float(contribution)
            except (ValueError, TypeError):
                continue

            participant_totals[name] += contribution

    # Sort highest contribution first
    participant_data = sorted(
        participant_totals.items(),
        key=lambda item: item[1],
        reverse=True,
    )

    # Optional: show only top N
    if top_n:
        participant_data = participant_data[:top_n]

    names = [item[0] for item in participant_data]
    totals = [item[1] for item in participant_data]

    # Short labels for display, full name in tooltip
    labels = [
        name if len(name) <= 35 else name[:32] + "..."
        for name in names
    ]

    fig = go.Figure(
        go.Bar(
            x=totals,
            y=labels,
            orientation="h",
            marker_color="#9076C0",
            text=[f"€{value:,.0f}" for value in totals],
            textposition="outside",
            customdata=names,
            hovertemplate=(
                "<b>%{customdata}</b><br>"
                "Total EU contribution: €%{x:,.2f}"
                "<extra></extra>"
            ),
        )
    )

    fig.update_layout(
        title="Total EU contribution of top 20 participants",
        xaxis_title="Total EU contribution (€)",
        yaxis_title="Participant",
        yaxis=dict(autorange="reversed"),
        height=max(500, len(names) * 35),
        margin=dict(l=250),
    )

    return fig

def plot_projects_by_country(projects):
    """
    Count the number of projects represented in each country.

    A project is counted once for a country, even if it has
    multiple participants from that country.
    """

    country_projects = defaultdict(set)

    for project in projects:

        project_id = project.get("id")

        if not project_id:
            continue

        for participant in project.get("participants", []):

            country = participant.get("country")

            if country:
                country_projects[country].add(project_id)

    # Number of unique projects per country
    country_data = sorted(
        country_projects.items(),
        key=lambda item: len(item[1]),
        reverse=True,
    )

    countries = [item[0] for item in country_data]
    project_counts = [len(item[1]) for item in country_data]

    # Chart
    fig = go.Figure(
        go.Bar(
            x=countries,
            y=project_counts,
            marker_color="#42F50B",
            text=project_counts,
            textposition="outside",
            hovertemplate=(
                "<b>%{x}</b><br>"
                "Projects: %{y}"
                "<extra></extra>"
            ),
        )
    )

    fig.update_layout(
        title="Number of projects by country",
        xaxis_title="Country",
        yaxis_title="Number of projects",
        height=550,
    )

    return fig

def create_project_collaboration_graph(projects, min_shared=1):
    """
    Create a PyVis graph showing collaboration between projects.

    Nodes:
        Project acronyms

    Edges:
        Two projects are connected when they share participants.

    Edge thickness:
        Number of participants shared by the two projects.

    Parameters
    ----------
    projects : list
        List of project dictionaries.

    min_shared : int
        Minimum number of shared participants required to create
        an edge.

    Returns
    -------
    Network
        PyVis network object.
    """

    net = Network(
        height="750px",
        width="100%",
        bgcolor="#ffffff",
        font_color="#333333",
        directed=False,
    )

    # --------------------------------------------------
    # Physics / layout
    # --------------------------------------------------

    net.set_options("""
    {
      "physics": {
        "enabled": true,
        "solver": "forceAtlas2Based",
        "forceAtlas2Based": {
          "gravitationalConstant": -80,
          "centralGravity": 0.01,
          "springLength": 180,
          "springConstant": 0.05,
          "damping": 0.4
        },
        "stabilization": {
          "enabled": true,
          "iterations": 1000
        }
      },
      "interaction": {
        "hover": true,
        "navigationButtons": true,
        "keyboard": true
      }
    }
    """)

    # --------------------------------------------------
    # Build project -> participants mapping
    # --------------------------------------------------

    project_participants = {}

    for project in projects:

        acronym = project.get("acronym")

        if not acronym:
            continue

        participants = set()

        for participant in project.get("participants", []):

            name = participant.get("legalName")

            if name:
                participants.add(name.strip())

        project_participants[acronym] = participants

    # --------------------------------------------------
    # Add project nodes
    # --------------------------------------------------

    for acronym, participants in project_participants.items():

        title = next(
            (
                p.get("title", "")
                for p in projects
                if p.get("acronym") == acronym
            ),
            "",
        )

        node_title = (
            f"{acronym}\n"
            f"Participants: {len(participants)}"
        )

        net.add_node(
            acronym,
            label=acronym,
            title=node_title,
            shape="dot",
            size=25,
            color={
                "background": "#F59E0B",
                "border": "#B45309",
                "highlight": {
                    "background": "#FBBF24",
                    "border": "#92400E",
                },
            },
            font={
                "size": 18,
                "face": "Arial",
                "bold": True,
            },
        )

    # --------------------------------------------------
    # Create edges between projects
    # --------------------------------------------------

    for (project_a, participants_a), (
        project_b,
        participants_b,
    ) in combinations(
        project_participants.items(),
        2,
    ):

        shared = participants_a & participants_b

        shared_count = len(shared)

        if shared_count < min_shared:
            continue

        shared_names = sorted(shared)

        edge_title = (
            f"Shared participants: {shared_count}\n"
            + "\n".join(f"- {name.lower().capitalize()}" for name in shared_names)
        )

        # Make thicker edge for more shared participants
        width = 1 + min(shared_count * 2, 15)

        net.add_edge(
            project_a,
            project_b,
            width=width,
            title=edge_title,
            label=str(shared_count),
            color={
                "color": "#D683B1",
                "highlight": "#C2410C",
                "hover": "#C2410C",
            },
        )

    return net