import logging
from typing import List, Dict, Any
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials
import base64
from email.mime.text import MIMEText
import google.auth
from google.cloud import bigquery
import os
from datetime import date


# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# Constants
ELIGIBLE_SHIPPING_METHODS = ["INSURED"]
ELIGIBLE_REASONS = ["DAMAGED", "NEVER_ARRIVED", "LOST"]

_, project_id = google.auth.default()
google_cloud_project = os.getenv("GOOGLE_CLOUD_PROJECT")
client = bigquery.Client(project=google_cloud_project)

# # Construct the query
# query = f"""
#     SELECT * FROM `{client.project}.refund_db.new_purchase_history`
# """

def get_purchase_history(purchaser: str) -> List[Dict[str, Any]]:
    """
    Retrieve purchase history for a given customer/order ID.

    Args:
        purchaser: Customer name or order ID fragment

    Returns:
        List of purchase records containing order details
    """
    purchaser = purchaser.strip().lower()
    logger.info(f"Retrieving purchase history for: {purchaser}")

    query = f"""
        SELECT
            customer_name,
            order_id,
            date,
            item.product_name,
            item.quantity,
            item.price,
            shipping_method,
            total_amount,
            customer_email_id
        FROM
            `{client.project}.refund_db.new_purchase_history`,
            UNNEST(items) AS item
        WHERE
          LOWER(customer_name) LIKE '%{purchaser}%'
    """

    try:
        query_job = client.query(query)
        results = query_job.result()

        
        history = []
        for row in results:
            row_dict = dict(row)
            # Convert date to string if it's a date object
            if isinstance(row_dict.get("date"), date):
                row_dict["date"] = row_dict["date"].isoformat()
            history.append(row_dict)


        if history:
            logger.info(f"Found {len(history)} purchase(s) for {purchaser}")
        else:
            logger.warning(f"No purchase history found for: {purchaser}")

        return history

    except Exception as e:
        logger.error(f"Error retrieving purchase history: {e}")
        return []



    """
    Retrieve purchase history for a given customer.

    Args:
        purchaser: Customer name

    Returns:
        List of purchase records containing order details
    """
    # Mock database of purchase history
    # Run the query
    # query_job = client.query(query)
    # results = query_job.result()
    
    # # Display results
    # if results.total_rows > 0:
    #     print(f"Found {results.total_rows} records in the purchase_history table:")
    #     for row in results:
    #         print(f"Customer ID: {row.user_id}, Date: {row.purchase_date}, Item: {row.item_name}, Amount: {row.price}")
    # else:
    #     print("No records found in the purchase_history table.")

    # Run the query
    query_job = client.query(query)
    history_data = query_job.result()
    print(history_data)
    
    # Display results
    if history_data.total_rows > 0:
        print(f"Found {history_data.total_rows} records in the purchase_history table:")
        # for row in results:
        #     print(f"Customer ID: {row.user_id}, Date: {row.purchase_date}, Item: {row.item_name}, Amount: {row.price}")
            
        # Convert results to JSON format
        # json_rows = []
        # for row in results:
        #     json_rows.append({
        #         "customer_name":row.customer_name,
        #         "order_id": row.order_id,
        #         "date": str(row.purchase_date),
        #         "item_name": row.item_name,
        #         "user_id": row.user_id,
        #         "item_name": row.item_name,
        #         "shipping_method": row.shipping_method,
        #         "total_amount": row.total_amount,
        #         "email_id": row.email_id
        #     })
    else:
        print("No records found in the purchase_history table.")

    # history_data = {
    #     "Alexis": [
    #         {
    #             "order_id": "JD001-20250415",
    #             "date": "2025-04-15",
    #             "items": [
    #                 {
    #                     "product_name": "Assorted Taffy 1lb Box",
    #                     "quantity": 1,
    #                     "price": 15.00,
    #                 },
    #                 {
    #                     "product_name": "Watermelon Taffy 0.5lb Bag",
    #                     "quantity": 1,
    #                     "price": 8.00,
    #                 },
    #             ],
    #             "shipping_method": "STANDARD",
    #             "total_amount": 23.00,
    #         }
    #     ],
    #     "David": [
    #         {
    #             "order_id": "SG002-20250610",
    #             "date": "2025-06-03",
    #             "items": [
    #                 {
    #                     "product_name": "Peanut Butter Taffy 0.5lb Bag",
    #                     "quantity": 1,
    #                     "price": 8.00,
    #                 },
    #                 {
    #                     "product_name": "Sour Apple Taffy 0.5lb Bag",
    #                     "quantity": 1,
    #                     "price": 8.00,
    #                 },
    #             ],
    #             "shipping_method": "INSURED",
    #             "total_amount": 16.00,
    #         },
    #     ],
    # }

    # Normalize purchaser name
    purchaser = purchaser.strip().title()

    logger.info(f"Retrieving purchase history for: {purchaser}")

    if purchaser not in history_data:
        logger.warning(f"No purchase history found for: {purchaser}")
        return []

    history = history_data[purchaser]
    logger.info(f"Found {len(history)} purchase(s) for {purchaser}")
    return history


def check_refund_eligibility(reason: str, shipping_method: str) -> bool:
    """
    Check if a refund request is eligible based on reason and shipping method.

    Args:
        reason: Refund reason
        shipping_method: Shipping method used for the order

    Returns:
        True if refund is eligible, False otherwise
    """
    reason_upper = reason.strip().upper()
    shipping_upper = shipping_method.strip().upper()

    logger.info(
        f"Checking refund eligibility - Reason: {reason_upper}, Shipping: {shipping_upper}"
    )

    # Check eligibility based on shipping method and reason
    is_eligible = (
        shipping_upper in ELIGIBLE_SHIPPING_METHODS and reason_upper in ELIGIBLE_REASONS
    )

    logger.info(f"Refund eligibility result: {is_eligible}")
    return is_eligible


def process_refund(amount: float, order_id: str) -> str:
    """
    Process a refund for the given amount and order.

    Args:
        amount: Refund amount in dollars
        order_id: Order ID to refund

    Returns:
        Success message with refund details
    """
    logger.info(f"Processing refund - Order: {order_id}, Amount: ${amount:.2f}")

    # In a real system, this would interact with payment processors
    # For now, we'll simulate a successful refund
    refund_id = f"REF-{order_id}-{int(amount*100)}"
    logger.info(f"Refund processed successfully - Refund ID: {refund_id}")

    return f"✅ Refund {refund_id} successful! We will credit ${amount:.2f} to your account within 2 business days."



def send_email_tool(to: str, subject: str, body: str) -> str:
    return send_email(to, subject, body)


# def send_email(to: str, subject: str, body: str) -> str:
#     creds = Credentials.from_service_account_file("/home/student_00_8e26a808a0c5/tools/service-account.json", scopes=["https://www.googleapis.com/auth/gmail.send"])
#     service = build("gmail", "v1", credentials=creds)

#     message = MIMEText(body)
#     message["to"] = "krishenndud@gmail.com"
#     message["subject"] = subject
#     raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
#     message_body = {"raw": raw}

#     sent = service.users().messages().send(userId="me", body=message_body).execute()
#     return f"Email sent to {to} with ID: {sent['id']}"

def send_email(to: str, subject: str, body: str) -> str:
    logger.info(f"Going to send mail to {to}")
    try:
        impersonated_user = "krishnendud@gmail.com"
        creds = Credentials.from_service_account_file("/home/student_00_8e26a808a0c5/tools/service-account.json", 
                scopes=["https://www.googleapis.com/auth/gmail.send"],                
                subject=impersonated_user
        )
        service = build("gmail", "v1", credentials=creds)

        message = MIMEText(body)
        message["to"] = to
        message["subject"] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        message_body = {"raw": raw}

        sent = service.users().messages().send(userId="me", body=message_body).execute()
        return f"Email sent to {to} with ID: {sent['id']}"
    except Exception as e:
        logger.error(f"Error sending email: {e}")
        return f"Error occured in sending mail to {to}"