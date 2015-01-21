from logging import handlers


class BufferingSMTPHandler(handlers.SMTPHandler):
    """
    BufferingSMTPHandler works like SMTPHandler log handler except that
    it buffers log messages until buffer size reaches or exceeds the specified
    capacity at which point it will then send everything that was buffered up
    until that point in one email message.  Contrast this with SMTPHandler
    which sends one email per log message received.
    """

    def __init__(self, mailhost, fromaddr, toaddrs, subject, credentials=None,
                 secure=None, capacity=1024):
        handlers.SMTPHandler.__init__(self, mailhost, fromaddr,
                                      toaddrs, subject,
                                      credentials, secure)

        self.capacity = capacity
        self.buffer = []

    def emit(self, record):
        try:
            self.buffer.append(record)

            if len(self.buffer) >= self.capacity:
                self.flush()
        except (KeyboardInterrupt, SystemExit):
            raise
        except:
            self.handleError(record)

    def flush(self):
        # buffer on termination may be empty if capacity is an exact multiple
        # of lines that were logged--thus we need to check for empty buffer
        if not self.buffer:
            return

        try:
            import smtplib
            from email.utils import formatdate
            port = self.mailport
            if not port:
                port = smtplib.SMTP_PORT
            smtp = smtplib.SMTP(self.mailhost, port)
            msg = ""
            for record in self.buffer:
                msg = msg + self.format(record) + "\r\n"
            msg = "From: %s\r\nTo: %s\r\nSubject: %s\r\nDate: %s\r\n\r\n%s" % (
                self.fromaddr,
                ",".join(self.toaddrs),
                self.getSubject(self.buffer[0]),
                formatdate(), msg)
            if self.username:
                if self.secure is not None:
                    smtp.ehlo()
                    smtp.starttls(*self.secure)
                    smtp.ehlo()
                smtp.login(self.username, self.password)
            smtp.sendmail(self.fromaddr, self.toaddrs, msg)
            smtp.quit()
            self.buffer = []
        except (KeyboardInterrupt, SystemExit):
            raise
        except:
            self.handleError(self.buffer[0])
