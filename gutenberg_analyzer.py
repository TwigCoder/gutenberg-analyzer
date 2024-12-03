import requests
from bs4 import BeautifulSoup
import pandas as pd
from textblob import TextBlob
import streamlit as st
import re
from time import sleep
import plotly.express as px
from collections import defaultdict
import numpy as np


def chunk_text(text, chunk_size=1000):
    return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]


@st.cache_data
def fetch_books():
    try:
        base_url = "https://www.gutenberg.org/browse/scores/top"
        response = requests.get(base_url)
        soup = BeautifulSoup(response.text, "html.parser")
        books = []

        for link in soup.select('a[href^="/ebooks/"]'):
            book_id = link["href"].split("/")[-1]
            if book_id.isdigit():
                title = link.text.strip()
                books.append({"id": book_id, "title": title})
                if len(books) >= 50:
                    break
                sleep(0.5)
        return books
    except Exception as e:
        st.error(f"Error fetching books: {str(e)}")
        return []


@st.cache_data
def fetch_book_content(book_id):
    try:
        url = f"https://www.gutenberg.org/files/{book_id}/{book_id}-0.txt"
        response = requests.get(url)
        text = response.text
        start = text.find("*** START OF")
        end = text.find("*** END OF")
        if start != -1 and end != -1:
            return text[start:end]
        return text[:5000]
    except Exception as e:
        return "Content not available in plain text format."


def analyze_sentiment_detailed(text):
    chunks = chunk_text(text)
    sentiments = []
    for chunk in chunks:
        blob = TextBlob(chunk)
        sentiments.append(
            {"polarity": blob.sentiment.polarity, "subjectivity": blob.subjectivity}
        )

    return {
        "overall_polarity": round(np.mean([s["polarity"] for s in sentiments]), 2),
        "overall_subjectivity": round(
            np.mean([s["subjectivity"] for s in sentiments]), 2
        ),
        "sentiment_progression": sentiments,
    }


def extract_book_metadata(content):
    lines = content.split("\n")
    author = "Unknown"
    year = "Unknown"

    author_patterns = [
        r"Author:\s*(.+)",
        r"by\s+([^,\n]+)",
        r"Written by\s+([^,\n]+)",
        r"By\s+([^,\n]+)",
    ]

    date_patterns = [
        r"Release Date:\s*.*?(\d{4})",
        r"\[.*?(\d{4})\]",
        r"Published.*?(\d{4})",
        r"Copyright.*?(\d{4})",
        r"First published.*?(\d{4})",
    ]

    content_start = 0
    for i, line in enumerate(lines):
        if "*** START OF" in line:
            content_start = i
            break

    header_text = "\n".join(lines[:content_start])

    for pattern in author_patterns:
        matches = re.search(pattern, header_text, re.IGNORECASE)
        if matches:
            author = matches.group(1).strip()
            # Clean up common artifacts
            author = re.sub(r"\s+", " ", author)
            author = re.sub(r"\[.*?\]", "", author)
            author = author.strip("., ")
            break

    for pattern in date_patterns:
        matches = re.search(pattern, header_text, re.IGNORECASE)
        if matches:
            year = matches.group(1)
            break

    return author, year


def main():
    st.set_page_config(page_title="Enhanced Gutenberg Analyzer", layout="wide")
    st.title("📚 Project Gutenberg Book Analyzer")

    with st.sidebar:
        st.header("Search & Filters")
        search_term = st.text_input("Search books by title").lower()

        st.header("Book Comparison")
        st.info("Select books below to compare their sentiment analysis")

    books = fetch_books()

    if search_term:
        books = [book for book in books if search_term in book["title"].lower()]

    col1, col2 = st.columns([2, 1])

    with col1:
        st.subheader("Available Books")
        for book in books:
            if st.button(f"📖 {book['title']}", key=book["id"]):
                st.session_state.selected_book = book["id"]
                st.session_state.book_content = fetch_book_content(book["id"])
                st.session_state.current_analysis = analyze_sentiment_detailed(
                    st.session_state.book_content
                )

                author, year = extract_book_metadata(st.session_state.book_content)
                st.session_state.current_metadata = {"author": author, "year": year}

    with col2:
        if st.checkbox("Add to comparison", key="compare"):
            if "comparison_books" not in st.session_state:
                st.session_state.comparison_books = []
            if st.session_state.get("selected_book"):
                if st.session_state.selected_book not in [
                    b["id"] for b in st.session_state.comparison_books
                ]:
                    st.session_state.comparison_books.append(
                        {
                            "id": st.session_state.selected_book,
                            "analysis": st.session_state.current_analysis,
                            "title": next(
                                book["title"]
                                for book in books
                                if book["id"] == st.session_state.selected_book
                            ),
                        }
                    )

    if hasattr(st.session_state, "selected_book"):
        st.header("Book Analysis")

        # Book metadata
        metadata = st.session_state.current_metadata
        st.markdown(f"**Author:** {metadata['author']} | **Year:** {metadata['year']}")

        # Tabs for different views
        tab1, tab2, tab3 = st.tabs(
            ["Content & Overview", "Sentiment Analysis", "Comparisons"]
        )

        with tab1:
            st.subheader("Book Excerpt")
            st.write(st.session_state.book_content[:1000] + "...")

            st.subheader("Quick Analysis")
            analysis = st.session_state.current_analysis
            col3, col4 = st.columns(2)
            with col3:
                st.metric("Overall Polarity", analysis["overall_polarity"])
            with col4:
                st.metric("Overall Subjectivity", analysis["overall_subjectivity"])

        with tab2:
            st.subheader("Detailed Sentiment Analysis")

            # Create sentiment progression plot
            progression = pd.DataFrame(analysis["sentiment_progression"])
            progression["chunk"] = range(len(progression))

            fig = px.line(
                progression,
                x="chunk",
                y=["polarity", "subjectivity"],
                title="Sentiment Progression Through Text",
                labels={"chunk": "Text Chunk", "value": "Score"},
            )
            st.plotly_chart(fig)

        with tab3:
            if (
                hasattr(st.session_state, "comparison_books")
                and len(st.session_state.comparison_books) > 0
            ):
                st.subheader("Book Comparisons")

                comparison_data = []
                for book in st.session_state.comparison_books:
                    comparison_data.append(
                        {
                            "Title": book["title"],
                            "Polarity": book["analysis"]["overall_polarity"],
                            "Subjectivity": book["analysis"]["overall_subjectivity"],
                        }
                    )

                comparison_df = pd.DataFrame(comparison_data)
                fig = px.bar(
                    comparison_df,
                    x="Title",
                    y=["Polarity", "Subjectivity"],
                    barmode="group",
                    title="Sentiment Comparison Across Books",
                )
                st.plotly_chart(fig)

                if st.button("Clear Comparisons"):
                    st.session_state.comparison_books = []
                    st.experimental_rerun()
            else:
                st.info("Add books to comparison using the checkbox above")


if __name__ == "__main__":
    main()

# SINCE I KEEP DELETING MY TERMINAL HISTORY AND FORGETTING: python3 -m streamlit run gutenberg_analyzer.py
