"""
Resume parsing service to extract candidate information.
"""
import re
import io
from typing import Dict, List, Optional
from fastapi import UploadFile
import PyPDF2
import docx


class ResumeParser:
    """Parse resumes to extract candidate information."""
    
    # Common skills keywords
    SKILLS_KEYWORDS = [
        'python', 'java', 'javascript', 'typescript', 'react', 'angular', 'vue',
        'node', 'django', 'flask', 'fastapi', 'express', 'spring', 'sql', 'nosql',
        'mongodb', 'postgresql', 'mysql', 'redis', 'docker', 'kubernetes', 'aws',
        'azure', 'gcp', 'git', 'ci/cd', 'jenkins', 'terraform', 'ansible',
        'html', 'css', 'sass', 'webpack', 'rest', 'graphql', 'microservices',
        'machine learning', 'deep learning', 'ai', 'data science', 'pandas',
        'numpy', 'tensorflow', 'pytorch', 'scikit-learn', 'nlp', 'computer vision'
    ]
    
    @staticmethod
    async def extract_text_from_pdf(file: UploadFile) -> str:
        """Extract text from PDF file."""
        try:
            content = await file.read()
            pdf_file = io.BytesIO(content)
            pdf_reader = PyPDF2.PdfReader(pdf_file)
            
            text = ""
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
            
            return text
        except Exception as e:
            raise ValueError(f"Failed to parse PDF: {str(e)}")
    
    @staticmethod
    async def extract_text_from_docx(file: UploadFile) -> str:
        """Extract text from DOCX file."""
        try:
            content = await file.read()
            doc = docx.Document(io.BytesIO(content))
            
            text = ""
            for paragraph in doc.paragraphs:
                text += paragraph.text + "\n"
            
            return text
        except Exception as e:
            raise ValueError(f"Failed to parse DOCX: {str(e)}")
    
    @staticmethod
    async def extract_text(file: UploadFile) -> str:
        """Extract text from resume file."""
        filename = file.filename.lower()
        
        if filename.endswith('.pdf'):
            return await ResumeParser.extract_text_from_pdf(file)
        elif filename.endswith('.docx'):
            return await ResumeParser.extract_text_from_docx(file)
        elif filename.endswith('.txt'):
            content = await file.read()
            return content.decode('utf-8')
        else:
            raise ValueError("Unsupported file format. Please upload PDF, DOCX, or TXT file.")
    
    @staticmethod
    def extract_email(text: str) -> Optional[str]:
        """Extract email address from text."""
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        matches = re.findall(email_pattern, text)
        return matches[0] if matches else None
    
    @staticmethod
    def extract_phone(text: str) -> Optional[str]:
        """Extract phone number from text."""
        # Match various phone formats
        phone_patterns = [
            r'\+?\d{1,3}[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}',
            r'\+?\d{10,15}',
            r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}'
        ]
        
        for pattern in phone_patterns:
            matches = re.findall(pattern, text)
            if matches:
                # Clean up the phone number
                phone = re.sub(r'[^\d+]', '', matches[0])
                return phone
        
        return None
    
    @staticmethod
    def extract_name(text: str) -> Optional[str]:
        """Extract name from text (usually first line)."""
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        if lines:
            # First non-empty line is usually the name
            name = lines[0]
            # Remove common titles
            name = re.sub(r'^(Mr\.|Ms\.|Mrs\.|Dr\.)\s+', '', name, flags=re.IGNORECASE)
            # Check if it looks like a name (2-4 words, no numbers)
            if len(name.split()) <= 4 and not re.search(r'\d', name):
                return name
        return None
    
    @staticmethod
    def extract_linkedin(text: str) -> Optional[str]:
        """Extract LinkedIn URL from text."""
        linkedin_pattern = r'(?:https?://)?(?:www\.)?linkedin\.com/in/[\w-]+'
        matches = re.findall(linkedin_pattern, text, re.IGNORECASE)
        return matches[0] if matches else None
    
    @staticmethod
    def extract_github(text: str) -> Optional[str]:
        """Extract GitHub URL from text."""
        github_pattern = r'(?:https?://)?(?:www\.)?github\.com/[\w-]+'
        matches = re.findall(github_pattern, text, re.IGNORECASE)
        return matches[0] if matches else None
    
    @staticmethod
    def extract_portfolio(text: str) -> Optional[str]:
        """Extract portfolio URL from text."""
        # Look for personal website URLs (excluding LinkedIn, GitHub, email providers)
        url_pattern = r'https?://(?!.*(?:linkedin|github|gmail|yahoo|outlook|hotmail))[\w.-]+\.(?:com|net|org|io|dev|me)'
        matches = re.findall(url_pattern, text, re.IGNORECASE)
        return matches[0] if matches else None
    
    @staticmethod
    def extract_skills(text: str) -> List[str]:
        """Extract skills from text."""
        text_lower = text.lower()
        found_skills = []
        
        for skill in ResumeParser.SKILLS_KEYWORDS:
            if skill.lower() in text_lower:
                # Capitalize first letter of each word
                formatted_skill = ' '.join(word.capitalize() for word in skill.split())
                if formatted_skill not in found_skills:
                    found_skills.append(formatted_skill)
        
        return found_skills[:15]  # Limit to 15 skills
    
    @staticmethod
    def extract_experience_years(text: str) -> Optional[int]:
        """Extract years of experience from text."""
        # Look for patterns like "5 years experience", "5+ years", "5 yrs"
        patterns = [
            r'(\d+)\+?\s*(?:years?|yrs?)\s*(?:of)?\s*(?:experience|exp)',
            r'experience:\s*(\d+)\+?\s*(?:years?|yrs?)',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                try:
                    return int(matches[0])
                except (ValueError, IndexError):
                    continue
        
        return None
    
    @staticmethod
    def extract_education(text: str) -> Optional[str]:
        """Extract education information from text."""
        # Look for degree keywords
        degree_keywords = [
            'bachelor', 'master', 'phd', 'doctorate', 'mba', 'b.tech', 'm.tech',
            'b.sc', 'm.sc', 'b.e', 'm.e', 'b.com', 'm.com', 'bca', 'mca'
        ]
        
        lines = text.split('\n')
        education_lines = []
        
        for i, line in enumerate(lines):
            line_lower = line.lower()
            if any(degree in line_lower for degree in degree_keywords):
                # Include this line and nearby context
                education_lines.append(line.strip())
                if i + 1 < len(lines):
                    education_lines.append(lines[i + 1].strip())
        
        if education_lines:
            return ' | '.join(filter(None, education_lines[:3]))  # Up to 3 lines
        
        return None
    
    @staticmethod
    def extract_location(text: str) -> Optional[str]:
        """Extract location from text."""
        # Look for city, state/country patterns
        location_pattern = r'(?:Location|Address|Based in):\s*([A-Za-z\s,]+)'
        matches = re.findall(location_pattern, text, re.IGNORECASE)
        if matches:
            return matches[0].strip()
        
        # Look for common location patterns in first few lines
        lines = [line.strip() for line in text.split('\n')[:10] if line.strip()]
        for line in lines:
            # Check if line contains city/state pattern
            if re.search(r'[A-Z][a-z]+,\s*[A-Z]{2}', line):
                return line
        
        return None
    
    @staticmethod
    async def parse_resume(file: UploadFile) -> Dict:
        """
        Parse resume and extract candidate information.
        
        Returns a dictionary with extracted fields.
        """
        # Extract text from file
        text = await ResumeParser.extract_text(file)
        
        # Extract all fields
        parsed_data = {
            "full_name": ResumeParser.extract_name(text),
            "email": ResumeParser.extract_email(text),
            "phone": ResumeParser.extract_phone(text),
            "linkedin_url": ResumeParser.extract_linkedin(text),
            "github_url": ResumeParser.extract_github(text),
            "portfolio_url": ResumeParser.extract_portfolio(text),
            "skills": ResumeParser.extract_skills(text),
            "years_of_experience": ResumeParser.extract_experience_years(text),
            "education": ResumeParser.extract_education(text),
            "location": ResumeParser.extract_location(text),
            "raw_text": text[:500]  # First 500 chars for reference
        }
        
        return parsed_data
