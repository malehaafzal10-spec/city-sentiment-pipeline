import spacy

def extract_locations_ml(text: str) -> list[str]:
    # Load the pre-trained English model
    nlp = spacy.load("en_core_web_sm")
    
    # Process the text
    doc = nlp(text)
    
    # Extract entities labeled as GPE (Geopolitical Entity) or LOC (Location)
    locations = [ent.text for ent in doc.ents if ent.label_ in ["GPE", "LOC"]]
    
    return locations

# Example usage
sample_text = "The best place is pakistan, frankfurt, but I also want to visit Tokyo."
print(extract_locations_ml(sample_text))
