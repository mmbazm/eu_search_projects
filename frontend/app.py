"""
EU Project Search - Frontend (Streamlit)

Page layout: two top-level columns.
- Left column: search box, country filter, and the list of matching
  project titles (radio selection).
- Right column: the selected project's summary, its participants table
  (with website links), and a map of participant locations (pydeck
  scatterplot, with legalName/city/country as tooltip).
"""


#Imports
import html
import os
import pandas as pd
import pydeck as pdk
import requests
import streamlit as st
import streamlit.components.v1 as components
import pycountry

#From
from datetime import datetime
from collections import defaultdict
from helpers import (
    create_collaboration_graph,
    create_country_collaboration_graph,
    plot_budget_vs_duration,
    plot_project_similarity,
    plot_project_timeline,
    plot_project_budgets,
    plot_projects_per_participant,
    plot_eu_contribution_by_country,
    plot_contribution_per_participant,
    plot_projects_by_country,
    create_project_collaboration_graph
)

#Variables
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
TITLE_COLOR = "#003399"  # EU flag blue

EU_COUNTRIES = {
    "Austria": "AT", "Belgium": "BE", "Bulgaria": "BG", "Croatia": "HR",
    "Cyprus": "CY", "Czechia": "CZ", "Denmark": "DK", "Estonia": "EE",
    "Finland": "FI", "France": "FR", "Germany": "DE", "Greece": "GR",
    "Hungary": "HU", "Ireland": "IE", "Italy": "IT", "Latvia": "LV",
    "Lithuania": "LT", "Luxembourg": "LU", "Malta": "MT", "Netherlands": "NL",
    "Poland": "PL", "Portugal": "PT", "Romania": "RO", "Slovakia": "SK",
    "Slovenia": "SI", "Spain": "ES", "Sweden": "SE",
}

COUNTRIES = {
    country.name: country.alpha_2
    for country in pycountry.countries
}

ALL_COUNTRIES_LABEL = "All countries"
ALL_PARTICIPANTS_LABEL = "All participants"
ALL_STATUS_LABEL = "All status"
FALLBACK_YEAR_RANGE = (2014, 2030)  # used only when no projects have a parseable date yet

#Functions
def _extract_year(date_str):
    """Best-effort: pulls a 4-digit year off the front of an ISO-ish date string."""
    if not date_str:
        return None
    try:
        return int(str(date_str)[:4])
    except (ValueError, TypeError):
        return None


def _year_range_slider(label, bounds, help_text):
    """Renders a range slider, or a static caption when there's only one distinct
    year (st.slider errors out if min_value == max_value)."""
    lo, hi = bounds
    if lo == hi:
        st.caption(f"{label}: only {lo} available")
        return (lo, hi)
    return st.slider(label, min_value=lo, max_value=hi, value=(lo, hi), help=help_text)

def calculate_total_funding(selected_projects):
    """
    Calculate total overall budget and EU contribution
    for the selected projects.
    """

    total_budget = 0.0
    total_eu_contribution = 0.0

    for project in selected_projects:

        # Overall budget
        budget = project.get("overall_budget")

        if budget is not None:
            try:
                total_budget += float(
                    str(budget)
                    .replace(",", "")
                    .replace("€", "")
                    .strip()
                )
            except (ValueError, TypeError):
                pass

        # EU contribution
        contribution = project.get("eu_contribution_amount")

        if contribution is not None:
            try:
                total_eu_contribution += float(
                    str(contribution)
                    .replace(",", "")
                    .replace("€", "")
                    .strip()
                )
            except (ValueError, TypeError):
                pass

    return total_budget, total_eu_contribution



st.set_page_config(page_title="EU Project Search", layout="wide")
st.title("🇪🇺 EU Funded Projects")

if "projects" not in st.session_state:
    st.session_state.projects = []

col_controls, col_detail = st.columns([1, 2])

all_projects = []

with col_controls:
    with st.form("search_form"):
        keyword = st.text_input(
            "Search a keyword",
            value="6G",
            help='Enter a keyword like "telco, 5G, edge computing.',
        )
        submitted = st.form_submit_button("Search")
    
    if not all_projects:
        st.info("Enter a keyword and click **Search** to see results.")

    if submitted and keyword.strip():
        with st.spinner("Searching EU projects..."):
            try:
                resp = requests.get(
                    f"{BACKEND_URL}/api/search",
                    params={"text": keyword.strip()},
                    timeout=100,
                )
                resp.raise_for_status()
                data = resp.json()
                st.session_state.projects = data.get("results", {}).get("projects", [])
                for warning in data.get("warnings", []):
                    st.warning(warning)
            except requests.exceptions.RequestException as exc:
                st.error(f"Search failed: {exc}")
                st.session_state.projects = []

    all_projects = st.session_state.projects

    for project in all_projects:
        for participant in project.get("participants", []):
            legal_name = participant.get("legalName")

            if legal_name:
                participant["legalName"] = legal_name.lower().capitalize()

    participant_names = sorted(
        {
            part.get("legalName")
            for p in all_projects
            for part in p.get("participants", [])
            if part.get("legalName")
        }
    )

    projects_status = sorted(
        {
            p.get("status")
            for p in all_projects
            if p.get("status")
        }
    )

    start_years = sorted(
        {y for p in all_projects if (y := _extract_year(p.get("start_date"))) is not None}
    )
    end_years = sorted(
        {y for p in all_projects if (y := _extract_year(p.get("end_date"))) is not None}
    )
    start_bounds = (min(start_years), max(start_years)) if start_years else FALLBACK_YEAR_RANGE
    end_bounds = (min(end_years), max(end_years)) if end_years else FALLBACK_YEAR_RANGE
    year_bounds = (min(start_years), max(end_years)) if start_years else FALLBACK_YEAR_RANGE

    with st.container(border=True):
        st.markdown("**Filters**")

        narrow_col, _ = st.columns([1, 1])
        with narrow_col:
            country_filter = st.selectbox(
                "Filter by participant country",
                options=[ALL_COUNTRIES_LABEL] + sorted(COUNTRIES.keys()),
                help="Only show projects that have at least one participant based in this country.",
            )

        narrow_col2, _ = st.columns([1, 1])
        with narrow_col2:
            participant_filter = st.selectbox(
                "Filter by participant",
                options=[ALL_PARTICIPANTS_LABEL] + participant_names,
                help="Only show projects that include this participant organisation.",
            )

        narrow_col3, _ = st.columns([1, 1])
        with narrow_col3:
            status_filter = st.selectbox(
                "Filter by status",
                options=[ALL_STATUS_LABEL] + projects_status,
                help="Only show projects with selected status.",
            )

        narrow_col6, _ = st.columns([1, 1])
        with narrow_col6:
            year_range = _year_range_slider(
                "Year range", year_bounds, "Only show projects whose start & end date falls in this range."
            )

    with st.container(border=True):
        projects = all_projects
        if country_filter != ALL_COUNTRIES_LABEL:
            selected_code = COUNTRIES[country_filter]
            projects = [
                p
                for p in projects
                if any(part.get("countryCode") == selected_code for part in p.get("participants", []))
            ]
        if participant_filter != ALL_PARTICIPANTS_LABEL:
            projects = [
                p
                for p in projects
                if any(part.get("legalName") == participant_filter for part in p.get("participants", []))
            ]
        if status_filter != ALL_STATUS_LABEL:
            projects = [
                p 
                for p in projects
                if p.get("status") == status_filter
            ]
        if year_range != year_bounds:
            lo, hi = year_range
            projects = [
                p for p in projects if (y := _extract_year(p.get("start_date"))) is not None and lo <= y <= hi and (y := _extract_year(p.get("end_date"))) is not None and lo <= y <= hi
            ]

        selected_idx = None

        if not projects:
            active_filters = []
            if country_filter != ALL_COUNTRIES_LABEL:
                active_filters.append(f"country = {country_filter}")
            if participant_filter != ALL_PARTICIPANTS_LABEL:
                active_filters.append(f"participant = {participant_filter}")
            if status_filter != ALL_STATUS_LABEL:
                active_filters.append(f"status = {status_filter}")
            if year_range != year_bounds:
                active_filters.append(f"year range = {year_range[0]}-{year_range[1]}")

            st.warning(f"No projects match {' and '.join(active_filters)} among the current results.")
        else:
            st.caption(f"{len(projects)} **project(s) found**")
            titles = [f"[{p.get('acronym') or '(no acronym)'}] {p.get('title') or '(untitled)'}" for p in projects]
            st.markdown("**Projects:**")
            selected_idx = st.radio(
                "",
                options=range(len(projects)),
                format_func=lambda i: titles[i],
                key=f"project_radio_{country_filter}_{participant_filter}",
                label_visibility="collapsed",
            )

with col_detail:
    with st.container(border=True):
        if selected_idx is None:
            st.info("Search results and project details will appear here.")
        else:
            project = projects[selected_idx]
            total_budget, total_eu = calculate_total_funding(projects)

            st.metric(
                "Total budget of all filtered projects:",
                f"€{total_budget:,.0f}"
            )
            st.metric(
                "Total EU contribution of all filtered projects:",
                f"€{total_eu:,.0f}"
            )                    
    with st.container(border=True):
        if selected_idx is None:
            st.info("Search results and project details will appear here.")
        else:
            project = projects[selected_idx]
            st.markdown(
                f'<h3 style="color:{TITLE_COLOR};">{html.escape(project.get("title") or "")}</h3>',
                unsafe_allow_html=True,
            )
            if project.get("url"):
                st.markdown(f"[Open project page]({project['url']})")
            st.markdown(f'**Summary:** {project.get("summary") or "_No summary available._"}')

            meta_row1 = st.columns(6)
            meta_row2 = st.columns(2)
            with meta_row1[0]:
                st.metric("Acronym", project.get("acronym") or "—")
            with meta_row1[1]:
                st.metric("Start date", project.get("start_date") or "—")
            with meta_row1[2]:
                st.metric("End date", project.get("end_date") or "—")
            with meta_row1[3]:
                st.metric("Status", project.get("status") or "—")
            with meta_row2[0]:
                st.metric("EU Contribution:", f"€{float(project.get("eu_contribution_amount")):,.0f}")
            with meta_row2[1]:
                st.metric("Overal Budget:", f"€{float(project.get("overall_budget")):,.0f}")

            participants = project.get("participants", [])
            st.markdown(f"**Participants: {len(participants)}**")

            if participants:
                df = pd.DataFrame(participants)
                st.dataframe(
                    df[["legalName", "city", "country", "website"]],
                    width="stretch",
                    hide_index=True,
                    column_config={
                        "legalName": "Participant",
                        "city": "City",
                        "country": "Country",
                        "website": st.column_config.LinkColumn("Website", display_text="Visit site"),
                    },
                )

                geo_df = df.dropna(subset=["latitude", "longitude"])
                if not geo_df.empty:
                    layer = pdk.Layer(
                        "ScatterplotLayer",
                        data=geo_df,
                        get_position="[longitude, latitude]",
                        get_radius=25000,
                        get_fill_color=[214, 39, 40, 200],
                        get_line_color=[255, 255, 255],
                        line_width_min_pixels=1,
                        pickable=True,
                    )
                    view_state = pdk.ViewState(
                        latitude=geo_df["latitude"].mean(),
                        longitude=geo_df["longitude"].mean(),
                        zoom=3,
                    )
                    st.pydeck_chart(
                        pdk.Deck(
                            map_style="road",  # Carto's natural-colour street style; the pydeck default ("dark") renders as a near-black map
                            layers=[layer],
                            initial_view_state=view_state,
                            tooltip = {
                                "text": "{legalName}\n{city}, {country}",
                                "style": {
                                    "backgroundColor": "#FFFFFF",
                                    "color": "#000000",
                                    "fontSize": "14px",
                                    "padding": "10px",
                                    "borderRadius": "6px",
                                    "border": "1px solid #000000",
                                },
                            }
                        )
                    )
                else:
                    st.warning("No coordinates available for this project's participants.")
            else:
                st.write("No participant data available.")
    
    with st.container(border=True):
        if selected_idx is None:
            st.info("Projects timeline will appear here.")
        else:
            start_year = min(start_years) # from line 214
            end_year = max(end_years)+1
            fig = plot_project_timeline(
                projects,
                start_year=start_year,
                end_year=end_year,
            )
            st.pyplot(fig)

    with st.container(border=True):
        st.markdown("**Collaboration Graph between Countries on the given projects:**")
        if selected_idx is None:
            st.info("collaboration graph will appear here.")
        else:
            net = create_country_collaboration_graph(
                projects,
                min_projects=1,
                top_n=20,
            )

            html = net.generate_html(notebook=False)

            components.html(
                html,
                height=750,
                scrolling=True,
            )

#    with st.container(border=True):
#        st.markdown("**Collaboration Graph between participants on the given projects:**")
#        if selected_idx is None:
#            st.info("collaboration graph will appear here.")
#        else:
#            print("")
#            net = create_collaboration_graph(projects)
#            html = net.generate_html(notebook=False)
#            components.html(html,height=750,scrolling=True,)


    with st.container(border=True):
        st.markdown("**Collaboration Graph between projects on the given list of participants:**")
        if selected_idx is None:
            st.info("Projects <--> Participants collaboration graph will appear here.")
        else:
            net = create_project_collaboration_graph(projects, min_shared=1,)
            html = net.generate_html(notebook=False)
            components.html(
                html,
                height=750,
                scrolling=True,
            )

    with st.container(border=True):
        with st.expander("ℹ️ How is project similarity calculated?"):

            st.markdown("""
            Similarity is based on the **Jaccard similarity** of participants:

            **Similarity = Shared participants / Unique participants across both projects**

            **Example:**

            - **Project A:** Nokia, Ericsson, Orange, Siemens
            - **Project B:** Nokia, Ericsson, Orange, IBM

            **Shared participants:** 3  
            **Unique participants:** 5  

            **Similarity = 3 / 5 = 60%**

            A value of **100%** means the two projects have exactly the same
            participants, while **0%** means they have no participants in common.
            """)
        if selected_idx is None:
            st.info("**Similarity based heatmap on the given projects:**")
        else:
            fig = plot_project_similarity(projects)

            st.plotly_chart(
                fig,
                width="stretch",
            )


    with st.container(border=True):
        if not projects:
            st.info("Projects budgets will appear here.")
        else:
            fig = plot_project_budgets(projects)

            st.plotly_chart(
                fig,
                width="stretch",
            )

    with st.container(border=True):
        if not projects:
            st.info("Project funding budget vs duration will appear here.")
        else:
            fig = plot_budget_vs_duration(projects)

            st.plotly_chart(
                fig,
                width="stretch",
            )

    with st.container(border=True):
        if not projects:
            st.info("Country vs Projects number chart will appear here.")
        else:
            fig = plot_projects_by_country(projects)

            st.plotly_chart(
                fig,
                width="stretch",
            )

    with st.container(border=True):
        if not projects:
            st.info("Participants vs Projects chart will appear here.")
        else:
            fig = plot_projects_per_participant(
                projects,
                top_n=20,
            )

            st.plotly_chart(
                fig,
                width="stretch",
            )

    with st.container(border=True):
        if not projects:
            st.info("Budget contribution chart per country will appear here.")
        else:
            fig = plot_eu_contribution_by_country(projects)

            st.plotly_chart(
                fig,
                width="stretch",
            )

    with st.container(border=True):
        if not projects:
            st.info("Budget contribution chart per participant will appear here.")
        else:
            fig = plot_contribution_per_participant(projects, top_n=20)

            st.plotly_chart(
                fig,
                width="stretch",
            )