import frappe
import requests
from frappe.utils import formatdate

@frappe.whitelist()
def export_purchase_order_to_v15(po_name):
	try:
		doc = frappe.get_doc("Purchase Order", po_name)
		config = frappe.get_single("PISPL Configuration")
		password = config.get_password('password')
		v15_url = config.url
		headers = {
			"Authorization": f"token {config.api_key}:{password}",
			"Content-Type": "application/json"
		}

		items = []
		for item in doc.items:
			v15_item_code = frappe.db.get_value(
				"Item Supplier",
				{"parent": item.item_code},
				"supplier_part_no"
			)

			items.append({
				"item_code": v15_item_code,
				"qty": item.qty,
				"rate": item.rate,
				"delivery_date": item.schedule_date.strftime("%Y-%m-%d") if item.schedule_date else None
			})
		
		taxes = []
		for tax in doc.taxes:
			taxes.append({
				"charge_type": tax.charge_type,
				"account_head": tax.account_head,
				"rate": tax.rate
			})

		payload = {
			"po_name": doc.name,
			"items": items,
			"taxes": taxes,
			"transaction_date": doc.transaction_date.strftime("%Y-%m-%d") if doc.transaction_date else None,
			"delivery_date": doc.schedule_date.strftime("%Y-%m-%d") if doc.schedule_date else None
		}

		frappe.log_error(title="payload", message=payload)

		response = requests.post(f"{v15_url}/api/method/proman.proman.utils.create_sales_order.create_sales_order", json=payload, headers=headers)

		if response.status_code == 200:
			try:
				response_data = response.json()  # Convert response to JSON
				frappe.log_error(title="Response Data", message=response_data)
				sales_order_id = response_data.get("message", {}).get("sales_order_id")
				frappe.log_error(title="SO Name", message=sales_order_id)

				# Update the Purchase Order in v13 with the Sales Order name
				frappe.db.set_value("Purchase Order", po_name, "so_name", sales_order_id)
				frappe.db.commit()  # Commit the changes

				frappe.log_error(f"{response.text}", "PO Export Success")
				return {"status": "success", "message": f"Sales Order created in PISPL v15 for PO {po_name}"}

			except json.JSONDecodeError:
				frappe.log_error(f"Invalid JSON response: {response.text}", "PO Export Error")
				return {"status": "error", "message": "Invalid response format from v15"}
					
		else:
			# Extract error message
			try:
				error_response = response.json()
				error_message = error_response.get("message", {}).get("error", "Unknown error occurred")
			except json.JSONDecodeError:
				error_message = response.text  # Fallback in case response is not JSON

			error_msg = f"Failed to export PO {po_name}: {error_message}"
			frappe.log_error(error_msg, "PO Export Error")
			return {"status": "error", "message": error_message}

	except Exception as e:
		error_msg = f"Error exporting PO {po_name}: {str(e)}"
		frappe.log_error(error_msg, "PO Export Error")
		return {"status": "error", "message": error_msg}

def validate_supplier_part_number(doc, method):

	"""Ensure all items have a Supplier Part Number when supplier is 'Proman Infrastructure Services Private Limited'"""
	
	supplier_name = "Proman Infrastructure Services Private Limited"
	
	if doc.supplier != supplier_name:
		return
	
	missing_items = []

	for item in doc.items:
		supplier_part_no = frappe.db.get_value(
			"Item Supplier",
			{"parent": item.item_code, "supplier": doc.supplier},
			"supplier_part_no"
		)

		if not supplier_part_no:
			missing_items.append(item.item_code)
	
	if missing_items:
		missing_items_str = ", ".join(missing_items)

		error_message = f"Missing Supplier Part Numbers in: {missing_items_str}"
		log = frappe.log_error(error_message, "Supplier Part Number missing")

		log_name = log.name if log else ""

		error_log_link = (
			f'<a href="/app/error-log/{log_name}" target="_blank">View Error Log</a>'
			if log_name
			else "Check Error Log for details."
		)

		error_message = f"Missing Supplier Part Numbers in: <br> {missing_items_str}"
		frappe.throw(f"{error_message}<br>{error_log_link}")
