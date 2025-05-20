from langchain.tools import tool
from datetime import datetime, timezone, timedelta
from typing import Dict, Union, Literal, Optional, Any, TypedDict
import json


class AddTimeParams(TypedDict, total=False):
    """Parameters for add_time operation"""
    days: int
    hours: int
    minutes: int


class SubtractTimeParams(TypedDict, total=False):
    """Parameters for subtract_time operation"""
    days: int
    hours: int
    minutes: int


class DurationParams(TypedDict):
    """Parameters for calculate_duration operation"""
    end_time: str


OperationType = Literal["add_time", "subtract_time", "calculate_duration"]


@tool
def calendar_math(
    operation: OperationType,
    time_value: str,
    parameters: Optional[Union[Dict[str, Any], str]] = None
) -> str:
    """
    Performs time calculations for appointment scheduling.
    
    Args:
        operation: The time calculation operation to perform:
            - add_time: Add days/hours/minutes to a datetime
            - subtract_time: Subtract days/hours/minutes from a datetime
            - calculate_duration: Calculate duration between two datetimes
        
        time_value: Base time value in ISO format (YYYY-MM-DDTHH:MM:SS)
        
        parameters: Additional parameters based on operation:
            - For add_time/subtract_time: {days: int, hours: int, minutes: int}
            - For calculate_duration: {end_time: str} (ISO format)
    
    Returns:
        For add_time/subtract_time: New datetime in ISO format
        For calculate_duration: JSON with total_seconds, hours, minutes
        For errors: JSON with error message
    
    Examples:
        Add 30 minutes: 
          calendar_math("add_time", "2023-01-01T10:00:00", {"minutes": 30})
          
        Calculate appointment duration:
          calendar_math("calculate_duration", "2023-01-01T10:00:00", 
                       {"end_time": "2023-01-01T11:30:00"})
    """
    # Handle parameters that might be passed as JSON string
    if parameters is None:
        parameters = {}
    elif isinstance(parameters, str):
        try:
            parameters = json.loads(parameters)
        except json.JSONDecodeError:
            return json.dumps({
                "error": f"Invalid parameters format. Expected valid JSON, got: {parameters}"
            })
    
    try:
        # Validate the time value
        try:
            dt = datetime.fromisoformat(time_value)
        except ValueError:
            return json.dumps({
                "error": f"Invalid time format: {time_value}. Use ISO format (YYYY-MM-DDTHH:MM:SS)"
            })
        
        # Add time operation
        if operation == "add_time":
            days = int(parameters.get("days", 0))
            hours = int(parameters.get("hours", 0))
            minutes = int(parameters.get("minutes", 0))
            
            if days == 0 and hours == 0 and minutes == 0:
                return json.dumps({
                    "warning": "No time added (days, hours, minutes all set to 0)",
                    "result": dt.isoformat()
                })
                
            result_dt = dt + timedelta(days=days, hours=hours, minutes=minutes)
            return result_dt.isoformat()
        
        # Subtract time operation
        elif operation == "subtract_time":
            days = int(parameters.get("days", 0))
            hours = int(parameters.get("hours", 0))
            minutes = int(parameters.get("minutes", 0))
            
            if days == 0 and hours == 0 and minutes == 0:
                return json.dumps({
                    "warning": "No time subtracted (days, hours, minutes all set to 0)",
                    "result": dt.isoformat()
                })
                
            result_dt = dt - timedelta(days=days, hours=hours, minutes=minutes)
            return result_dt.isoformat()
        
        # Calculate duration operation
        elif operation == "calculate_duration":
            end_time = parameters.get("end_time")
            if not end_time:
                return json.dumps({
                    "error": "Missing required parameter: end_time"
                })
            
            try:
                end_dt = datetime.fromisoformat(end_time)
            except ValueError:
                return json.dumps({
                    "error": f"Invalid end_time format: {end_time}. Use ISO format (YYYY-MM-DDTHH:MM:SS)"
                })
            
            # Ensure end time is after start time
            if end_dt < dt:
                return json.dumps({
                    "error": "End time must be after start time",
                    "start_time": time_value,
                    "end_time": end_time
                })
                
            duration = end_dt - dt
            total_seconds = duration.total_seconds()
            
            return json.dumps({
                "total_seconds": total_seconds,
                "hours": int(total_seconds // 3600),
                "minutes": int((total_seconds % 3600) // 60),
                "seconds": int(total_seconds % 60)
            })
        
        # Invalid operation
        else:
            return json.dumps({
                "error": f"Invalid operation: {operation}",
                "valid_operations": ["add_time", "subtract_time", "calculate_duration"]
            })
            
    except Exception as e:
        return json.dumps({
            "error": f"Error processing time calculation: {str(e)}"
        })

