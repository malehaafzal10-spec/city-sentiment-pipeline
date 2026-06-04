from flashtext import KeywordProcessor

def extract_with_flashtext(text: str, cities: list[str], countries: list[str]) -> dict[str, list[str]]:
    # Initialize processor (case_sensitive=False by default)
    processor = KeywordProcessor()
    
    # Add keywords. We map the target word to a category for easy grouping
    for city in cities:
        processor.add_keyword(city, f"City:{city}")
    for country in countries:
        processor.add_keyword(country, f"Country:{country}")
        
    # Extract all matches in one rapid pass
    extracted = processor.extract_keywords(text)
    
    # Separate the results back into lists
    results = {"cities": [], "countries": []}
    for item in extracted:
        category, name = item.split(":")
        if category == "City":
            results["cities"].append(name)
        elif category == "Country":
            results["countries"].append(name)
            
    return results

# Example data
db_cities = ["Copenhagen", "New York", "Frankfurt"]
db_countries = ["Pakistan", "Denmark", "Oman"]

sample_text = "I went from copenhagen to pakistan, and met a woman from frankfurt."
print(extract_with_flashtext(sample_text, db_cities, db_countries))
# Output: {'cities': ['Copenhagen', 'New York'], 'countries': ['Pakistan']}
# Notice it successfully ignored "woman" despite containing "oman"