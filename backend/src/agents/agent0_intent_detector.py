"""
Agent 0: Intent Detection & Conversational Agent

This agent:
1. Handles generic conversation with users
2. Detects when user wants troubleshooting/debugging
3. Decides whether to show form or continue chatting
"""

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
import os
import json
import re


class IntentAgent:
    def __init__(self):
        self.llm = ChatOpenAI(
            model="llama3:8b-instruct-q2_K",
            temperature=0.7,
            api_key="ollama",
            base_url="http://localhost:11434/v1",
             model_kwargs={"response_format": {"type": "json_object"}}
        )
    
    def extract_json(self, text: str) -> dict:
        """
        Robustly extract JSON from LLM response text.
        Handles markdown code blocks, extra text, and various edge cases.
        """
        # Remove any leading/trailing whitespace
        text = text.strip()
        
        # Method 1: Try direct JSON parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        
        # Method 2: Extract from markdown code blocks
        # Pattern: ```json ... ``` or ``` ... ```
        code_block_pattern = r'```(?:json)?\s*(\{.*?\})\s*```'
        matches = re.findall(code_block_pattern, text, re.DOTALL)
        if matches:
            try:
                return json.loads(matches[0])
            except json.JSONDecodeError:
                pass
        
        # Method 3: Find JSON object in text (look for {...})
        json_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
        matches = re.findall(json_pattern, text, re.DOTALL)
        
        # Try each match, starting from the longest
        for match in sorted(matches, key=len, reverse=True):
            try:
                return json.loads(match)
            except json.JSONDecodeError:
                continue
        
        # Method 4: Try to find and extract between first { and last }
        try:
            start = text.index('{')
            end = text.rindex('}') + 1
            json_text = text[start:end]
            return json.loads(json_text)
        except (ValueError, json.JSONDecodeError):
            pass
        
        # If all methods fail, raise error
        raise json.JSONDecodeError(f"Could not extract valid JSON from text: {text[:200]}...", text, 0)
    
    def analyze_intent(self, user_message: str, conversation_history: list = None) -> dict:
        """
        Analyze user message to determine intent and generate appropriate response.
        
        Args:
            user_message: The user's input message
            conversation_history: Previous messages in the conversation
            
        Returns:
            dict with:
                - intent: 'troubleshoot', 'general_chat', 'clarification_needed'
                - response: LLM-generated response
                - show_form: bool indicating if form should be shown
                - confidence: float 0-1 indicating confidence in intent detection
        """
        
        # Build conversation context
        messages = []
        if conversation_history:
            for msg in conversation_history[-5:]:  # Last 5 messages for context
                messages.append({
                    "role": msg.get("role", "user"),
                    "content": msg.get("content", "")
                })
        
        # Add current user message
        messages.append({
            "role": "user",
            "content": user_message
        })
        
        # System prompt for intent detection
        system_prompt = """You are an AI assistant that helps with troubleshooting and general conversation.

CRITICAL: You MUST respond with ONLY a valid JSON object. No other text, no markdown, no explanations outside the JSON.

Your tasks:
1. Determine the user's intent from their message
2. Provide a helpful, natural response
3. Classify the intent as one of:
   - "troubleshoot": User wants to debug/troubleshoot an application issue
   - "general_chat": User wants general conversation, questions, or information
   - "clarification_needed": User's intent is unclear, need more information

TROUBLESHOOTING INDICATORS:
- Keywords: "error", "bug", "issue", "problem", "not working", "broken", "fail", "crash", "debug", "troubleshoot", "investigate", "fix", "logs", "exception"
- Phrases: "help me debug", "something is wrong", "having an issue", "need to investigate"
- Context: Describing technical problems, asking for help with errors

GENERAL CHAT INDICATORS:
- Questions about: how things work, explanations, general information
- Greetings: "hello", "hi", "hey"
- Casual conversation

REQUIRED JSON FORMAT (respond with ONLY this, nothing else):
{
  "intent": "troubleshoot|general_chat|clarification_needed",
  "response": "Your natural, helpful response to the user",
  "show_form": true or false,
  "confidence": 0.0 to 1.0,
  "reasoning": "Brief explanation of why you classified this way"
}

RULES:
- Output ONLY valid JSON, no additional text
- Be conversational and helpful in the "response" field
- If intent is troubleshooting with high confidence (>0.7), set show_form=true
- If unsure, ask clarifying questions (show_form=false)
- For general chat, provide helpful responses (show_form=false)
- Always be polite and professional

Examples:

User: "My application is throwing NullPointerException errors"
{"intent":"troubleshoot","response":"I can help you investigate that NullPointerException. To properly analyze the issue, I'll need some information about your application. Would you like me to help you debug this?","show_form":true,"confidence":0.95,"reasoning":"Clear technical issue with specific error mentioned"}

User: "Hello, what can you do?"
{"intent":"general_chat","response":"Hi! I'm an AI troubleshooting assistant. I can help you:\\n\\n🔍 Debug application issues and errors\\n📊 Analyze logs to find root causes\\n💡 Suggest fixes for technical problems\\n🤖 I work with a multi-agent system to provide comprehensive analysis\\n\\nAre you experiencing any issues with your application, or do you have questions about how I work?","show_form":false,"confidence":1.0,"reasoning":"Greeting and information request, not a troubleshooting need"}

User: "It's not working"
{"intent":"clarification_needed","response":"I'd be happy to help! To better assist you, could you provide more details?\\n\\n• What exactly is not working?\\n• What application or system are you referring to?\\n• What error messages are you seeing?\\n• When did this issue start?","show_form":false,"confidence":0.6,"reasoning":"Vague problem statement needs clarification"}"""
        
        try:
            # Build LangChain messages
            langchain_messages = [SystemMessage(content=system_prompt)]
            
            # Add conversation history
            for msg in messages:
                if msg["role"] == "user":
                    langchain_messages.append(HumanMessage(content=msg["content"]))
                elif msg["role"] == "assistant":
                    langchain_messages.append(AIMessage(content=msg["content"]))
            
            # Call ChatOpenAI for intent detection (with JSON mode enabled)
            response = self.llm.invoke(langchain_messages)
            
            # Extract response text
            response_text = response.content.strip()
            
            # Use robust JSON extraction
            result = self.extract_json(response_text)
            
            # Validate and set defaults
            result.setdefault("intent", "general_chat")
            result.setdefault("show_form", False)
            result.setdefault("confidence", 0.5)
            result.setdefault("reasoning", "")
            
            # Ensure response field exists and is a string
            if "response" not in result or not isinstance(result["response"], str):
                result["response"] = "I'm here to help! Could you tell me more about what you need?"
            
            return result
            
        except json.JSONDecodeError as e:
            print(f"❌ Failed to parse JSON response: {e}")
            print(f"📄 Raw response text: {response_text[:500]}")
            
            # Fallback response
            return {
                "intent": "general_chat",
                "response": "I understand. Could you tell me more about what you need help with?",
                "show_form": False,
                "confidence": 0.3,
                "reasoning": "Failed to parse intent, falling back to general chat"
            }
            
        except Exception as e:
            print(f"Error in intent detection: {e}")
            
            # Fallback response
            return {
                "intent": "general_chat",
                "response": "I'm here to help! What would you like assistance with?",
                "show_form": False,
                "confidence": 0.3,
                "reasoning": f"Error occurred: {str(e)}"
            }
    
    def handle_conversation(self, user_message: str, conversation_history: list = None) -> dict:
        """
        Main entry point for handling user conversations.
        
        This wraps analyze_intent with additional logic and formatting.
        """
        result = self.analyze_intent(user_message, conversation_history)
        
        # Add metadata
        result["timestamp"] = None  # Will be set by API
        result["user_message"] = user_message
        
        return result


# Example usage
if __name__ == "__main__":
    agent = IntentAgent()
    
    # Test cases
    test_messages = [
        "Hello, how are you?",
        "My application is throwing errors in production",
        "I need help debugging a NullPointerException",
        "What's the weather like?",
        "It's broken",
        "Can you help me investigate why my service is crashing?"
    ]
    
    print("Testing Intent Agent:")
    print("=" * 80)
    
    for msg in test_messages:
        print(f"\n📝 User: {msg}")
        result = agent.analyze_intent(msg)
        print(f"🎯 Intent: {result['intent']}")
        print(f"💬 Response: {result['response']}")
        print(f"📋 Show Form: {result['show_form']}")
        print(f"📊 Confidence: {result['confidence']:.2f}")
        print(f"🤔 Reasoning: {result['reasoning']}")
        print("-" * 80)