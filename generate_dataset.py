import os
import pandas as pd
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

def compute_jaccard(str1: str, str2: str) -> float:
    """Computes Jaccard similarity for comma-separated categorical tags."""
    set1 = set(x.strip().lower() for x in str(str1).split(',') if x.strip())
    set2 = set(x.strip().lower() for x in str(str2).split(',') if x.strip())
    if not set1 or not set2:
        return 0.0
    return len(set1.intersection(set2)) / len(set1.union(set2))

def compute_skill_overlap(student_skills: str, required_skills: str) -> float:
    """Calculates the ratio of required skills fulfilled by the student."""
    s_set = set(x.strip().lower() for x in str(student_skills).split(',') if x.strip())
    r_set = set(x.strip().lower() for x in str(required_skills).split(',') if x.strip())
    if not r_set:
        return 1.0
    return len(s_set.intersection(r_set)) / len(r_set)

def generate_pairwise_features(students_path: str = "students.csv", 
                               researchers_path: str = "data/researchers.csv", 
                               output_path: str = "data/matching_topk_labeled.csv"):
    os.makedirs(os.path.dirname(researchers_path), exist_ok=True)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Ensure researchers.csv exists
    if not os.path.exists(researchers_path):
        researchers_data = [
            {"researcher_id": "R001", "name": "Dr. Alice Smith", "department": "Computer Science & AI",
             "research_areas": "Artificial Intelligence, Natural Language Processing, Machine Learning",
             "expertise": "Large Language Models, Deep Learning, NLP",
             "required_skills": "Python, PyTorch, Transformers",
             "project_description": "Building conversational AI and semantic search engines using LLMs.",
             "publication_summary": "Transformers in Natural Language Processing and Deep Learning."},
            {"researcher_id": "R002", "name": "Dr. Bob Jones", "department": "Computer Vision & Medical Imaging",
             "research_areas": "Computer Vision, Deep Learning, Image Processing",
             "expertise": "CNNs, Object Detection, Image Segmentation",
             "required_skills": "Python, OpenCV, PyTorch, TensorFlow",
             "project_description": "Real-time object detection and diagnostic image segmentation.",
             "publication_summary": "Convolutional Neural Networks for Automated Vision."},
            {"researcher_id": "R003", "name": "Dr. Carol White", "department": "Cybersecurity & Networking",
             "research_areas": "Cybersecurity, Network Security, Machine Learning",
             "expertise": "Intrusion Detection, Threat Detection",
             "required_skills": "Python, Machine Learning, Networking, Linux",
             "project_description": "ML-based network intrusion detection and zero-day threat analysis.",
             "publication_summary": "Advanced Cybersecurity and Anomaly Detection."},
            {"researcher_id": "R004", "name": "Prof. Rajesh Kumar", "department": "Data Structures & Analytics",
             "research_areas": "Data Structures, Algorithms, Big Data, Database Systems",
             "expertise": "Advanced DSA, Predictive Analytics, Database Systems",
             "required_skills": "C++, Java, Python, SQL, Data Structures",
             "project_description": "Optimizing graph algorithms and high-throughput data processing pipelines.",
             "publication_summary": "Efficient Data Structures for Large-Scale Graph Analytics."},
            {"researcher_id": "R005", "name": "Dr. David Brown", "department": "Cloud Computing & Systems",
             "research_areas": "Cloud Computing, Distributed Systems, Big Data",
             "expertise": "Cloud Architecture, Microservices, Scalable Processing",
             "required_skills": "Python, Docker, Kubernetes, Spark",
             "project_description": "Containerized microservices and automated scaling in cloud networks.",
             "publication_summary": "Distributed Processing and Kubernetes Orchestration."}
        ]
        pd.DataFrame(researchers_data).to_csv(researchers_path, index=False)

    students_df = pd.read_csv(students_path)
    researchers_df = pd.read_csv(researchers_path)
    
    rows = []
    for _, s in students_df.iterrows():
        s_text = f"{s['research_areas']} {s['expertise']} {s['skills']} {s['projects']} {s['publications']}"
        
        for _, r in researchers_df.iterrows():
            r_text = f"{r['research_areas']} {r['expertise']} {r['required_skills']} {r['project_description']} {r['publication_summary']}"
            
            tfidf = TfidfVectorizer().fit_transform([s_text, r_text])
            tfidf_sim = float(cosine_similarity(tfidf[0:1], tfidf[1:2])[0][0])
            semantic_sim = min(1.0, tfidf_sim + 0.10)
            
            ra_sim = compute_jaccard(s['research_areas'], r['research_areas'])
            exp_sim = compute_jaccard(s['expertise'], r['expertise'])
            skill_sim = compute_skill_overlap(s['skills'], r['required_skills'])
            
            proj_tfidf = TfidfVectorizer().fit_transform([str(s['projects']), str(r['project_description'])])
            proj_sim = float(cosine_similarity(proj_tfidf[0:1], proj_tfidf[1:2])[0][0])
            
            pub_tfidf = TfidfVectorizer().fit_transform([str(s['publications']), str(r['publication_summary'])])
            pub_sim = float(cosine_similarity(pub_tfidf[0:1], pub_tfidf[1:2])[0][0])
            
            dept_match = 1 if "Computer Science" in str(r.get('department', '')) else 0
            label = 1 if (skill_sim >= 0.5 or (ra_sim >= 0.3 and tfidf_sim >= 0.2)) else 0
            
            rows.append({
                "student_id": s['student_id'],
                "researcher_id": r['researcher_id'],
                "tfidf_similarity": tfidf_sim,
                "semantic_similarity": semantic_sim,
                "research_area_similarity": ra_sim,
                "expertise_similarity": exp_sim,
                "skill_overlap": skill_sim,
                "project_similarity": proj_sim,
                "publication_similarity": pub_sim,
                "department_match": dept_match,
                "relevance_label": label
            })

    df_out = pd.DataFrame(rows)
    df_out.to_csv(output_path, index=False)
    print(f"Features generated: {df_out.shape[0]} candidate pairs saved to {output_path}")

if __name__ == "__main__":
    generate_pairwise_features()