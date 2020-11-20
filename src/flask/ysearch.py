from app import app

if __name__=='__main__':
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    app.config['SECRET_KEY'] = '123456'
    app.run(debug=True)

