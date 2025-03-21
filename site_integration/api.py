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

			error_msg = f"Failed to create SO for the PO {po_name}: {error_message}"
			frappe.log_error(error_msg, "SO Creation Error")
			return {"status": "error", "message": error_message}

	except requests.ConnectionError:
		error_msg = f"Could not connect to PISPL v15 site. Please ensure the site is running and try again."
		frappe.log_error(error_msg, "v15 Connection Error on SO creation")
		frappe.throw(error_msg)
	
	except Exception as e:
		error_msg = f"Error creating SO for the PO {po_name}: {str(e)}"
		frappe.log_error(error_msg, "SO Creation Error")
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

def cancel_sales_order_in_v15(doc, method):
	supplier_name = "Proman Infrastructure Services Private Limited"
	
	if doc.supplier != supplier_name:
		return
	
	try:
		if not doc.so_name:
			frappe.msgprint("No linked Sales Order found in PISPL site")
			return

		# Fetch v15 API credentials
		config = frappe.get_single("PISPL Configuration")
		password = config.get_password('password')
		v15_url = config.url

		headers = {
			"Authorization": f"token {config.api_key}:{password}",
			"Content-Type": "application/json"
		}

		payload = {"sales_order_name": doc.so_name}

		response = requests.post(f"{v15_url}/api/method/proman.proman.utils.create_sales_order.cancel_sales_order", json=payload, headers=headers)

		if response.status_code == 200:
			response_data = response.json()
			frappe.log_error(title="SO Cancel Success in PISPL v15", message=response_data)
			frappe.msgprint(f"Sales Order {doc.so_name} cancelled in PISPL v15 too!")
			return

		else:
			error_response = response.json()
			error_message = error_response.get("message", "Unknown error occurred")
			frappe.log_error(f"Failed to cancel SO {doc.so_name}: {error_message}", "SO Cancel Error")
			frappe.throw(f"Sales Order {doc.so_name} cancellation failed in PISPL v15")
			return

	except requests.ConnectionError:
		error_msg = f"Could not connect to PISPL v15 site. Please ensure the site is running before cancelling the PO."
		frappe.log_error(error_msg, "v15 Connection Error on SO Cancel")
		frappe.throw(error_msg)

	except Exception as e:
		frappe.log_error(f"Error canceling SO {doc.so_name}: {str(e)}", "SO Cancel Error2")
		frappe.throw(f"Error canceling Sales Order {doc.so_name} in PISPL v15")

def export_amended_purchase_order_to_v15(po_name):
	try:
		frappe.log_error(title="Amending PO")
		doc = frappe.get_doc("Purchase Order", po_name)
		
		config = frappe.get_single("PISPL Configuration")
		password = config.get_password('password')
		v15_url = config.url

		headers = {
			"Authorization": f"token {config.api_key}:{password}",
			"Content-Type": "application/json"
		}

		# Ensure the PO has a linked SO
		if not doc.so_name:
			frappe.msgprint("No linked Sales Order found in PISPL site.")
			return

		items = []
		for item in doc.items:
			# v15_item_code = frappe.db.get_value(
			# 	"Item Supplier",
			# 	{"parent": item.item_code},
			# 	"supplier_part_no"
			# )

			items.append({
				"item_code": item.supplier_part_no,
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
			"old_so_name": doc.so_name,  # Pass old SO name for reference
			"new_po_name": doc.name,  # New amended PO name
			"items": items,
			"taxes": taxes,
			"transaction_date": doc.transaction_date.strftime("%Y-%m-%d") if doc.transaction_date else None,
			"delivery_date": doc.schedule_date.strftime("%Y-%m-%d") if doc.schedule_date else None
		}

		response = requests.post(f"{v15_url}/api/method/proman.proman.utils.create_sales_order.amend_sales_order", json=payload, headers=headers)

		if response.status_code == 200:
			response_data = response.json()
			curr_so_name = doc.so_name
			frappe.log_error(title="Response Data", message=response_data)
			new_sales_order_id = response_data.get("message", {}).get("new_sales_order_id")

			# if new_sales_order_id:
			frappe.db.set_value("Purchase Order", po_name, "so_name", new_sales_order_id)
			frappe.db.commit()

			# return {"status": "success", "message": f"Amended Sales Order {new_sales_order_id} created for PO {po_name}"}

			frappe.msgprint(f"Sales Order {curr_so_name} amended in PISPL v15 too!")

		else:
			error_message = response.json().get("message", "Unknown error occurred")
			frappe.log_error(f"Failed to amend PO {po_name}: {error_message}", "PO Amend Error")
			return {"status": "error", "message": error_message}

	except requests.ConnectionError:
		error_msg = f"Could not connect to PISPL v15 site. Ensure the site is running before amending the PO."
		frappe.log_error(error_msg, "v15 Connection Error on PO amend")
		frappe.throw(error_msg)
	
	except Exception as e:
		frappe.log_error(f"Error amending PO {po_name}: {str(e)}", "PO Amend Error")
		frappe.throw(f"Error amending PO {po_name} in PISPL v15")

def trigger_po_amendment_sync(doc, method):
	frappe.log_error(title="Triggering PO amendment sync")
	"""Hook function to trigger amendment sync when a PO is amended."""
	if doc.amended_from:
		export_amended_purchase_order_to_v15(doc.name)
		doc.reload()
