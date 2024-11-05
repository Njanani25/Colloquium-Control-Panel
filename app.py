import mysql.connector
from flask import Flask, request, render_template, redirect, url_for, Response, send_file, jsonify
import csv
import os
from io import StringIO
import logging
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch

app = Flask(__name__)


# Set up logging
logging.basicConfig(level=logging.DEBUG)

# Ensure there's a directory for the CSV file
os.makedirs('data', exist_ok=True)

#--------------------------Index page-----------------------------------------------------------
@app.route('/', methods=['GET', 'POST'])
def renderLoginPage():
    events = runQuery("SELECT * FROM events")
    branchs = runQuery("SELECT * FROM branch")  # Renamed for consistency

    if request.method == 'POST':
        # Gather form data
        Name = request.form['FirstName'] + " " + request.form['LastName']
        Mobile = request.form['MobileNumber']
        Branch_id = request.form['Branch']
        Event = request.form['Event']
        Email = request.form['Email']

        # Validate inputs
        if len(Mobile) != 10 or not Mobile.isdigit():
            return render_template('loginfail.html', errors=["Invalid Mobile Number!"])
        
        if not Email.endswith('.com'):
            return render_template('loginfail.html', errors=["Invalid Email!"])
        
        # Check if the student is already registered
        existing_participants = runQuery("SELECT * FROM participants WHERE event_id={} AND mobile='{}'".format(Event, Mobile))
        if len(existing_participants) > 0:
            return render_template('loginfail.html', errors=["Student already Registered for the Event!"])
        
        # Check if the participant count has been fulfilled
        current_count = runQuery("SELECT COUNT(*) FROM participants WHERE event_id={}".format(Event))[0][0]
        max_count = runQuery("SELECT participants FROM events WHERE event_id={}".format(Event))[0][0]
        
        if current_count >= max_count:
            return render_template('loginfail.html', errors=["Participants count fulfilled already!"])

        # Prepare the insert query
        insert_query = "INSERT INTO participants(event_id, fullname, email, mobile, college, branch_id) VALUES({}, '{}', '{}', '{}', 'VCEW', '{}')".format(Event, Name, Email, Mobile, Branch_id)

        try:
            # Execute the insert query
            runQuery(insert_query)
            return render_template('index.html', events=events, branchs=branchs, errors=["Successfully Registered!"])
        except Exception as e:
            # Log the error for debugging
            print(f"Error during registration: {e}")
            return render_template('loginfail.html', errors=["An error occurred during registration. Please try again."])

    return render_template('index.html', events=events, branchs=branchs)

#--------------------------------------admin page------------------------------------------------
@app.route('/admin', methods=['GET', 'POST'])
def renderAdmin():
    if request.method == 'POST':
        UN = request.form['username']
        PS = request.form['password']

        cred = runQuery("SELECT * FROM admin")
        for user in cred:
            if UN == user[0] and PS == user[1]:
                return redirect('/events')

        return render_template('admin.html', errors=["Wrong Username/Password"])

    return render_template('admin.html')

#----------------------------------events page------------------------------------------------------
@app.route('/events', methods=['GET', 'POST'])
def getEvents():
    eventTypes = runQuery("SELECT *,(SELECT COUNT(*) FROM participants AS P WHERE T.type_id IN (SELECT type_id FROM events AS E WHERE E.event_id = P.event_id)) AS COUNT FROM event_type AS T;") 
    events = runQuery("SELECT event_id, event_title, (SELECT COUNT(*) FROM participants AS P WHERE P.event_id = E.event_id) AS count FROM events AS E;")
    types = runQuery("SELECT * FROM event_type;")
    location = runQuery("SELECT * FROM location")

    if request.method == "POST":
        try:
            Name = request.form["newEvent"]
            fee = request.form["Fee"]
            participants = request.form["maxP"]
            Type = request.form["EventType"]
            Location = request.form["EventLocation"]
            Date = request.form['Date']
            runQuery("INSERT INTO events(event_title, event_price, participants, type_id, location_id, date) VALUES(\"{}\", {}, {}, {}, {}, \'{}\');".format(Name, fee, participants, Type, Location, Date))
        except Exception as e:
            logging.error("Error adding new event: %s", e)
            EventId = request.form.get("EventId")
            if EventId:
                runQuery("DELETE FROM events WHERE event_id={}".format(EventId))

    return render_template('events.html', events=events, eventTypes=eventTypes, types=types, locations=location)

#---------------------------------------events info page-----------------------------------------------
@app.route('/eventsinfo')
def rendereventinfo():  
    events = runQuery("SELECT *,(SELECT COUNT(*) FROM participants AS P WHERE P.event_id = E.event_id ) AS count FROM events AS E LEFT JOIN event_type USING(type_id) LEFT JOIN location USING(location_id);")
    return render_template('eventsinfo.html', events=events)

#-------------------------------------participants page------------------------------------------------------
@app.route('/participants', methods=['GET', 'POST'])
def renderParticipants():
    events = runQuery("SELECT * FROM events;")
    selected_event = None
    participants = []
    if request.method == "POST":
        selected_event = request.form['Event']
        participants = runQuery("SELECT p_id, fullname, mobile, email FROM participants WHERE event_id={}".format(selected_event))
    return render_template('participants.html', events=events, participants=participants, selected_event=selected_event)


#------------------------------------download specific event participants-------------------------------------
@app.route('/download-participants')
def download_participants():
    selected_event = request.args.get('event')
    
    if selected_event is None:
        logging.error("No event selected for download")
        return "No event selected", 400

    participants = runQuery("SELECT p_id, fullname, mobile, email FROM participants WHERE event_id={}".format(selected_event))

    if not participants:
        logging.warning("No participants found for event ID: %s", selected_event)
        return "No participants found for this event", 404

    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(['Participant ID', 'Name', 'Contact', 'Email'])  # Header row
    cw.writerows(participants)  # Data rows

    response = Response(si.getvalue(), mimetype='text/csv')
    response.headers['Content-Disposition'] = 'attachment; filename=participants.csv'
    return response

#-------------------------------download all participants-------------------------------------------------------

@app.route('/download-all-participants')
def download_all_participants():
    # Query to fetch all participants across all events
    query = "SELECT p_id, fullname, mobile, email, event_id FROM participants"
    participants = runQuery(query)

    if not participants:
        logging.warning("No participants found in the database.")
        return "No participants found", 404

    # Create a CSV in memory
    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(['Participant ID', 'Name', 'Contact', 'Email', 'Event ID'])  # Header row
    cw.writerows(participants)  # Data rows
    si.seek(0)  # Reset pointer to the beginning of the StringIO object

    # Prepare the response
    response = Response(si.getvalue(), mimetype='text/csv')
    response.headers['Content-Disposition'] = 'attachment; filename=all_participants.csv'
    return response

#-------------------------------feedback page--------------------------------------------------------------------
@app.route('/feedback_form', methods=['GET', 'POST']) 
def feedback_form():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        feedback = request.form.get('feedback')
        
        # Debugging print statements
        print(f"Received feedback from {name} ({email}): {feedback}")

        # Here you would typically handle the feedback data (e.g., save it to a database)

        # Generate the certificate
        return jsonify({"message": "Feedback received", "name": name})

    return render_template('feedback_form.html')  # Display feedback form
    

@app.route('/download-sheet', methods=['GET'])
def download_sheet():
    return send_file('data/feedback.csv', as_attachment=True)


#-------------------------------download e-certificate--------------------------------------------------------------
@app.route('/download-certificate', methods=['GET'])
def download_certificate():
    name = request.args.get('name', 'Participant').upper()  # Convert name to uppercase
    event_name = "VIVEKA FEST 2025"
    event_dates = "between January 1 - January 5, 2025"
    logo_path = 'static/images/awardlogo.png'  # Path to your logo image
    background_image_path = 'static/images/certificatepage1.jpg'  # Path to your background image

    # Define square certificate size (e.g., 600x600 points)
    certificate_size = 500
    certificate_path = f'data/{name}_certificate.pdf'

    try:
        # Create the certificate with square size
        c = canvas.Canvas(certificate_path, pagesize=(certificate_size, certificate_size))

        # Draw background image
        if os.path.exists(background_image_path):
            c.drawImage(background_image_path, 0, 0, width=certificate_size, height=certificate_size)  # Full page background
        else:
            print(f"Background image not found at: {background_image_path}")

        # Draw border
        c.setStrokeColor(colors.black)
        c.setLineWidth(2)
        c.rect(10, 10, certificate_size - 20, certificate_size - 20)  # Rectangle for border

        # Title
        c.setFont("Helvetica-Bold", 28)
        c.setFillColor('#FFD700')  # Set font color to gold
        c.drawCentredString(certificate_size / 2, certificate_size - 50, "CERTIFICATE")

        # Event Name
        c.setFont("Helvetica-Bold", 22)
        c.drawCentredString(certificate_size / 2, certificate_size - 100, event_name)

        # Add space after the event name
        text_y = certificate_size - 130  # Starting Y position after event name

        # Award Text with indentation
        c.setFont("Helvetica", 14)
        c.setFillColor('#000000')  # Set font color to black

        # Formatted award text
        text = (
            f"This certificate is awarded to {name} in recognition of their active "
            f"participation in {event_name} {event_dates}. Your participation, enthusiasm, "
            "and dedication have been an integral part of the success of the event, and we are "
            "pleased to recognize your involvement."
        )

        # Draw award text with proper alignment and spacing
        text_x = 20  # Indentation space for the award text
        text_y = certificate_size - 150  # Starting Y position for the award text
        text_width = certificate_size - 30  # Width for the text area

        # Split text into lines to fit within the defined width
        text_lines = []
        current_line = []
        for word in text.split():
            current_line.append(word)
            line_width = c.stringWidth(' '.join(current_line), 'Helvetica', 14)
            if line_width > text_width:  # Check if line exceeds width
                current_line.pop()  # Remove last word
                text_lines.append(' '.join(current_line))  # Add to lines
                current_line = [word]  # Start new line with the last word
        text_lines.append(' '.join(current_line))  # Add any remaining words

        # Draw each line of the award text with added line spacing
        line_spacing = 25  # Space between lines
        for line in text_lines:
            c.drawString(text_x, text_y, line)
            text_y -= line_spacing  # Move down for the next line

        # Highlight participant's name in uppercase and bold
        c.setFont("Helvetica-Bold", 16)  # Use bold font for the name
        c.setFillColor('#FFD700')  # Set font color to gold for the name
       

        # Logo
        if os.path.exists(logo_path):
            c.drawImage(logo_path, (certificate_size - 200) / 2, 100, width=200, height=100)  # Centered logo
        else:
            print(f"Logo not found at: {logo_path}")

        c.save()

        # Send the generated certificate to the user
        return send_file(certificate_path, as_attachment=True)

    except Exception as e:
        print(f"Error generating certificate: {e}")
        return jsonify({"error": "Internal server error occurred while generating the certificate."}), 500




#-----------------------------------------------------------------------------------------------------------------
def runQuery(query):
    try:
        db = mysql.connector.connect(host='localhost', database='event_horizon', user='root', password='')
        
        if db.is_connected():
            cursor = db.cursor(buffered=True)
            cursor.execute(query)
            db.commit()
            res = None
            try:
                res = cursor.fetchall()
            except Exception as e:
                logging.error("Query returned no results: %s", e)
                return []
            return res

    except mysql.connector.Error as e:
        logging.error("MySQL Error: %s", e)
        return []

    except Exception as e:
        logging.error("Unexpected error: %s", e)
        return []

    finally:
        if db.is_connected():
            db.close()

if __name__ == "__main__":
    app.run(debug=True)
